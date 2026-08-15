"""
test_media_processing_embeddings.py

1. Unit tests (mocked DB session, no PostgreSQL) -- pipeline non-fatal
   behavior, concurrency lock, per-video helpers
2. Integration tests (real PostgreSQL + pgvector, require TEST_DATABASE_URL)
   -- vector persistence and backfill through an actual session/transaction
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, ProcessingStatus, SubtitleSource
from app.models.processing_log import ProcessingLog
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.processing.ffmpeg_processor import ProcessingError
from app.services import media_processing_service


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1,
        owner_id=1,
        title="Test video",
        original_filename="test.mp4",
        file_path="videos/1/test.mp4",
        file_size_bytes=1024,
        mime_type="video/mp4",
        status=MediaStatus.PROCESSING,
        source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
        has_subtitles=True,
        has_embeddings=False,
    )
    defaults.update(overrides)
    return Video(**defaults)


def _make_user(**overrides) -> User:
    defaults = dict(
        full_name="Test User",
        username="testuser",
        email="test@example.com",
        password_hash="not-a-real-hash",
    )
    defaults.update(overrides)
    return User(**defaults)


# ===========================================================================
# 1. Unit tests -- mocked DB session, no PostgreSQL
# ===========================================================================

# process_video: non-fatal embedding failure
def test_process_video_reaches_ready_when_embedding_fails(mocker):
    video = _make_video()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = video
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)

    mocker.patch.object(media_processing_service, "_extract_metadata")
    # _generate_transcript resolves the transcript via the uploaded ->
    # embedded -> Whisper precedence chain; patch it directly.
    mocker.patch.object(media_processing_service, "_generate_transcript", return_value=[])
    mocker.patch.object(
        media_processing_service,
        "_generate_embeddings_for_video",
        side_effect=ProcessingError("embedding model unavailable"),
    )

    media_processing_service.process_video(1)

    # Metadata and transcription both "succeeded" (no-op mocks, no
    # exception), embedding failed -- the video must still end up READY,
    # per the explicit non-fatal requirement for this stage.
    assert video.status == MediaStatus.READY
    assert video.processing_error is None
    mock_db.close.assert_called_once()


def test_process_video_reaches_ready_on_unexpected_embedding_exception(mocker):
    # Same as above, but for the catch-all Exception branch rather than a
    # ProcessingError -- both paths must leave status/processing_error
    # untouched, unlike the metadata/whisper stages' catch-alls.
    video = _make_video()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = video
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)

    mocker.patch.object(media_processing_service, "_extract_metadata")
    mocker.patch.object(media_processing_service, "_generate_transcript", return_value=[])
    mocker.patch.object(
        media_processing_service,
        "_generate_embeddings_for_video",
        side_effect=RuntimeError("out of memory"),
    )

    media_processing_service.process_video(1)

    assert video.status == MediaStatus.READY
    assert video.processing_error is None


def test_process_video_reaches_ready_when_embedding_succeeds(mocker):
    video = _make_video()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = video
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)

    mocker.patch.object(media_processing_service, "_extract_metadata")
    mocker.patch.object(media_processing_service, "_generate_transcript", return_value=[])
    mocker.patch.object(media_processing_service, "_generate_embeddings_for_video")

    media_processing_service.process_video(1)

    assert video.status == MediaStatus.READY
    assert video.processing_error is None


def test_process_video_metadata_failure_stays_failed_and_skips_embedding(mocker):
    # Contrast case: a failure in an earlier stage (metadata) must still
    # behave the old way -- video FAILED, embedding stage never reached.
    video = _make_video()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = video
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)

    mocker.patch.object(
        media_processing_service, "_extract_metadata", side_effect=ProcessingError("file missing")
    )
    mock_transcript = mocker.patch.object(media_processing_service, "_generate_transcript", return_value=[])
    mock_embed = mocker.patch.object(media_processing_service, "_generate_embeddings_for_video")

    media_processing_service.process_video(1)

    assert video.status == MediaStatus.FAILED
    assert video.processing_error == "file missing"
    mock_transcript.assert_not_called()
    mock_embed.assert_not_called()


def test_process_video_returns_early_when_video_missing(mocker):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)
    mock_extract = mocker.patch.object(media_processing_service, "_extract_metadata")

    media_processing_service.process_video(999)

    mock_extract.assert_not_called()
    mock_db.close.assert_called_once()


# _generate_embeddings_for_video
def test_generate_embeddings_for_video_assigns_vectors_to_segments(mocker):
    video = _make_video()
    segments = [
        TranscriptSegment(id=1, video_id=1, start_time=0.0, end_time=1.0, text="hello", source=SubtitleSource.WHISPER),
        TranscriptSegment(id=2, video_id=1, start_time=1.0, end_time=2.0, text="world", source=SubtitleSource.WHISPER),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = segments

    fake_vectors = [[0.1] * 384, [0.2] * 384]
    mocker.patch.object(media_processing_service.embedding_processor, "generate_embeddings", return_value=fake_vectors)

    media_processing_service._generate_embeddings_for_video(mock_db, video)

    assert segments[0].embedding == fake_vectors[0]
    assert segments[1].embedding == fake_vectors[1]
    assert video.has_embeddings is True


def test_generate_embeddings_for_video_no_segments_is_vacuously_complete(mocker):
    video = _make_video()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    generate_spy = mocker.patch.object(media_processing_service.embedding_processor, "generate_embeddings")

    media_processing_service._generate_embeddings_for_video(mock_db, video)

    generate_spy.assert_not_called()
    assert video.has_embeddings is True


# retry_missing_embeddings: concurrency + recheck-after-lock
def test_retry_missing_embeddings_skips_when_lock_already_held(mocker):
    mock_db = MagicMock()
    assert media_processing_service._backfill_lock.acquire(blocking=False)
    try:
        processed_count = media_processing_service.retry_missing_embeddings(mock_db)
        assert processed_count == 0
        # Lock held elsewhere -- must return before ever querying videos.
        mock_db.query.assert_not_called()
    finally:
        media_processing_service._backfill_lock.release()


def test_retry_missing_embeddings_rechecks_and_skips_already_embedded_video(mocker):
    video = _make_video(has_embeddings=False)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [video]

    # Simulate a concurrent process_video() completing this video's
    # embedding stage between the query above and this loop reaching it --
    # db.refresh flips the in-memory flag, which the recheck must honor.
    def _refresh(obj):
        obj.has_embeddings = True

    mock_db.refresh.side_effect = _refresh
    generate_spy = mocker.patch.object(media_processing_service, "_generate_embeddings_for_video")

    processed_count = media_processing_service.retry_missing_embeddings(mock_db)

    assert processed_count == 0
    generate_spy.assert_not_called()
    assert media_processing_service._backfill_lock.locked() is False


def test_retry_missing_embeddings_processes_and_completes_video(mocker):
    video = _make_video(has_embeddings=False)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [video]
    mock_db.refresh.side_effect = lambda obj: None  # no-op, flag unchanged
    mocker.patch.object(media_processing_service, "_generate_embeddings_for_video")

    processed_count = media_processing_service.retry_missing_embeddings(mock_db)

    assert processed_count == 1
    assert media_processing_service._backfill_lock.locked() is False


def test_retry_missing_embeddings_continues_past_a_failing_video(mocker):
    video_a = _make_video(id=1, has_embeddings=False)
    video_b = _make_video(id=2, has_embeddings=False)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [video_a, video_b]
    mock_db.refresh.side_effect = lambda obj: None

    def _generate(db, video):
        if video.id == 1:
            raise ProcessingError("model failed")

    mocker.patch.object(media_processing_service, "_generate_embeddings_for_video", side_effect=_generate)

    processed_count = media_processing_service.retry_missing_embeddings(mock_db)

    # video_a failed and was skipped (continue), video_b still processed --
    # one bad video in a backfill batch shouldn't stop the rest.
    assert processed_count == 1
    assert media_processing_service._backfill_lock.locked() is False


def test_retry_missing_embeddings_releases_lock_even_on_unexpected_error(mocker):
    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("db exploded")

    with pytest.raises(RuntimeError):
        media_processing_service.retry_missing_embeddings(mock_db)

    # The `finally: _backfill_lock.release()` must run regardless -- a
    # crash here must never leave the lock permanently held.
    assert media_processing_service._backfill_lock.locked() is False


def test_backfill_missing_embeddings_task_swallows_unexpected_errors(mocker):
    # This is the entry point run in a background thread (startup task and
    # admin endpoint both use it) -- an uncaught exception here would
    # otherwise vanish silently, so it must be caught and logged, not
    # propagated.
    mock_db = MagicMock()
    mocker.patch.object(media_processing_service, "SessionLocal", return_value=mock_db)
    mocker.patch.object(
        media_processing_service, "retry_missing_embeddings", side_effect=RuntimeError("boom")
    )

    media_processing_service.backfill_missing_embeddings_task()  # must not raise

    mock_db.close.assert_called_once()


# ===========================================================================
# 2. Integration tests -- real PostgreSQL + pgvector (TEST_DATABASE_URL)
# ===========================================================================

def test_generate_embeddings_persists_vectors_to_postgres(pg_session, mocker):
    user = _make_user()
    pg_session.add(user)
    pg_session.flush()

    video = _make_video(id=None, owner_id=user.id)
    pg_session.add(video)
    pg_session.flush()

    segment = TranscriptSegment(
        video_id=video.id, start_time=0.0, end_time=1.0, text="hello world", source=SubtitleSource.WHISPER
    )
    pg_session.add(segment)
    pg_session.flush()

    fake_vector = [0.5] * 384
    mocker.patch.object(
        media_processing_service.embedding_processor, "generate_embeddings", return_value=[fake_vector]
    )

    media_processing_service._generate_embeddings_for_video(pg_session, video)
    pg_session.commit()

    pg_session.expire_all()
    persisted_segment = pg_session.get(TranscriptSegment, segment.id)
    persisted_video = pg_session.get(Video, video.id)

    assert persisted_segment.embedding is not None
    assert len(persisted_segment.embedding) == 384
    assert persisted_video.has_embeddings is True


def test_retry_missing_embeddings_backfills_existing_ready_video_in_postgres(pg_session, mocker):
    user = _make_user(username="backfilluser", email="backfill@example.com")
    pg_session.add(user)
    pg_session.flush()

    # Simulates a video uploaded before this feature existed: READY,
    # has_embeddings defaults False, already has transcript segments.
    video = _make_video(id=None, owner_id=user.id, status=MediaStatus.READY, has_embeddings=False)
    pg_session.add(video)
    pg_session.flush()

    segment = TranscriptSegment(
        video_id=video.id, start_time=0.0, end_time=1.0, text="pre-existing segment", source=SubtitleSource.WHISPER
    )
    pg_session.add(segment)
    pg_session.commit()

    fake_vector = [0.25] * 384
    mocker.patch.object(
        media_processing_service.embedding_processor, "generate_embeddings", return_value=[fake_vector]
    )

    processed_count = media_processing_service.retry_missing_embeddings(pg_session)
    pg_session.commit()

    assert processed_count == 1

    pg_session.expire_all()
    persisted_video = pg_session.get(Video, video.id)
    persisted_segment = pg_session.get(TranscriptSegment, segment.id)

    assert persisted_video.has_embeddings is True
    assert persisted_segment.embedding is not None
    assert len(persisted_segment.embedding) == 384

    completed_log = (
        pg_session.query(ProcessingLog)
        .filter(
            ProcessingLog.video_id == video.id,
            ProcessingLog.process_type == media_processing_service.PROCESS_TYPE_EMBEDDING,
        )
        .first()
    )
    assert completed_log is not None
    assert completed_log.status == ProcessingStatus.COMPLETED
