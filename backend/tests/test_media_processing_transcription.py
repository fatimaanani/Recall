"""
test_media_processing_transcription.py

Integration tests (real PostgreSQL via pg_session, same convention as
test_media_processing_elasticsearch_sync.py) for
media_processing_service._generate_transcript -- specifically, that it now
routes Whisper's raw segment output through
app/processing/transcript_segmenter.py before persisting TranscriptSegment
rows (2026-08-08), rather than writing each raw Whisper segment boundary
directly. whisper_processor.extract_audio/transcribe_audio are mocked
(no real audio file, no real Whisper model); evaluate_segment/
is_hallucination_dominated/transcript_segmenter itself all run for real,
against real settings thresholds, exactly as process_video would call
them.

1. Shared helpers
2. Fragmented segments are merged into fewer rows
3. Well-separated segments stay distinct
4. has_subtitles / subtitle_source set correctly
5. No reliable speech still raises ProcessingError, no rows written
6. Reprocessing captures removed_segment_ids and replaces old rows
7. Source precedence -- uploaded subtitle skips Whisper entirely
8. Source precedence -- embedded subtitle skips Whisper entirely
9. Source precedence -- a failed uploaded subtitle falls through to Whisper
"""

from __future__ import annotations

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.processing.ffmpeg_processor import ProcessingError
from app.processing.whisper_processor import WhisperSegment
from app.services import media_processing_service


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(
        full_name="Transcription User", username=f"transcuser{id(overrides)}",
        email=f"transc{id(overrides)}@example.com", password_hash="x",
    )
    defaults.update(overrides)
    user = User(**defaults)
    pg_session.add(user)
    pg_session.flush()
    return user


def _pg_make_video(pg_session, owner_id, **overrides) -> Video:
    defaults = dict(
        owner_id=owner_id, title="Transcription Video", original_filename="v.mp4",
        file_path=f"videos/{owner_id}/v.mp4", file_size_bytes=1024, mime_type="video/mp4",
        status=MediaStatus.PROCESSING, source_type=MediaSourceType.USER_UPLOAD, visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    pg_session.add(video)
    pg_session.flush()
    return video


def _whisper_segment(start: float, end: float, text: str) -> WhisperSegment:
    # Comfortably within every default acceptance threshold (see
    # whisper_processor.evaluate_segment) -- these tests are about
    # segmentation, not hallucination filtering, which already has its
    # own dedicated coverage in test_speech_to_text_search.py.
    return WhisperSegment(
        start=start, end=end, text=text, no_speech_prob=0.1, avg_logprob=-0.2, compression_ratio=1.2,
    )


def _mock_extraction(mocker, tmp_path, video: Video) -> None:
    # Real files on pytest's own tmp_path rather than mocking
    # pathlib.Path.exists globally -- same convention test_clip_service.py
    # uses, and safer than patching a stdlib method that pg_session/other
    # fixtures might also rely on during the same test.
    mocker.patch.object(media_processing_service.settings, "storage_root", str(tmp_path))
    mocker.patch.object(media_processing_service.settings, "processing_temp_dir", str(tmp_path / "tmp"))
    source_path = tmp_path / video.file_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"fake source bytes")
    mocker.patch.object(media_processing_service.whisper_processor, "extract_audio")


# ===========================================================================
# 2. Fragmented segments are merged into fewer rows
# ===========================================================================

def test_fragmented_whisper_segments_are_merged_into_one_row(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    pg_session.commit()

    _mock_extraction(mocker, tmp_path, video)
    # 0.1s and 0.05s gaps -- both well under the default 0.5s merge
    # threshold (app/config.py's transcript_segment_merge_gap_seconds).
    mocker.patch.object(
        media_processing_service.whisper_processor, "transcribe_audio",
        return_value=[
            _whisper_segment(0.0, 1.0, "the quick"),
            _whisper_segment(1.1, 2.0, "brown fox"),
            _whisper_segment(2.05, 3.0, "jumps"),
        ],
    )

    media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    segments = (
        pg_session.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video.id)
        .order_by(TranscriptSegment.start_time)
        .all()
    )
    assert len(segments) == 1
    assert segments[0].text == "the quick brown fox jumps"
    assert segments[0].start_time == 0.0
    assert segments[0].end_time == 3.0


# ===========================================================================
# 3. Well-separated segments stay distinct
# ===========================================================================

def test_well_separated_segments_are_not_merged(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    pg_session.commit()

    _mock_extraction(mocker, tmp_path, video)
    mocker.patch.object(
        media_processing_service.whisper_processor, "transcribe_audio",
        return_value=[
            _whisper_segment(0.0, 1.0, "first sentence"),
            _whisper_segment(10.0, 12.0, "a much later sentence"),
        ],
    )

    media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    segments = (
        pg_session.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video.id)
        .order_by(TranscriptSegment.start_time)
        .all()
    )
    assert len(segments) == 2
    assert segments[0].text == "first sentence"
    assert segments[1].text == "a much later sentence"


# ===========================================================================
# 4. has_subtitles / subtitle_source
# ===========================================================================

def test_has_subtitles_and_subtitle_source_set_after_transcription(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    pg_session.commit()

    _mock_extraction(mocker, tmp_path, video)
    mocker.patch.object(
        media_processing_service.whisper_processor, "transcribe_audio",
        return_value=[_whisper_segment(0.0, 1.0, "hello")],
    )

    media_processing_service._generate_transcript(pg_session, video)

    assert video.has_subtitles is True
    assert video.subtitle_source == SubtitleSource.WHISPER


# ===========================================================================
# 5. No reliable speech still raises, no rows written
# ===========================================================================

def test_no_speech_detected_raises_and_writes_nothing(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    pg_session.commit()

    _mock_extraction(mocker, tmp_path, video)
    mocker.patch.object(media_processing_service.whisper_processor, "transcribe_audio", return_value=[])

    try:
        media_processing_service._generate_transcript(pg_session, video)
        raised = False
    except ProcessingError:
        raised = True
    assert raised

    pg_session.rollback()
    count = pg_session.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).count()
    assert count == 0


# ===========================================================================
# 6. Reprocessing captures removed_segment_ids and replaces old rows
# ===========================================================================

def test_reprocessing_removes_old_whisper_segments_and_reports_their_ids(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    old_segment = TranscriptSegment(
        video_id=video.id, start_time=0.0, end_time=1.0, text="stale transcript",
        source=SubtitleSource.WHISPER,
    )
    pg_session.add(old_segment)
    pg_session.commit()
    old_segment_id = old_segment.id

    _mock_extraction(mocker, tmp_path, video)
    mocker.patch.object(
        media_processing_service.whisper_processor, "transcribe_audio",
        return_value=[_whisper_segment(0.0, 1.0, "fresh transcript")],
    )

    removed_ids = media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    assert removed_ids == [old_segment_id]
    remaining = (
        pg_session.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video.id)
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].text == "fresh transcript"
    assert remaining[0].id != old_segment_id


# ===========================================================================
# 7. Source precedence -- uploaded subtitle skips Whisper entirely
# ===========================================================================

def test_uploaded_subtitle_is_used_and_whisper_is_never_called(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(
        pg_session, user.id,
        subtitle_source=SubtitleSource.UPLOADED,
        subtitle_path=f"subtitles/{user.id}/captions.srt",
    )
    pg_session.commit()

    mocker.patch.object(media_processing_service.settings, "storage_root", str(tmp_path))
    subtitle_abs_path = tmp_path / video.subtitle_path
    subtitle_abs_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_abs_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nUploaded subtitle text.\n", encoding="utf-8"
    )
    # Source file itself only needs to exist for the initial check --
    # embedded-subtitle probing runs against it too, but real ffprobe on
    # this fake content harmlessly fails closed (see probe_embedded_
    # subtitle_stream_index's own docstring) and falls through, which
    # never happens here anyway since the uploaded branch succeeds first.
    source_path = tmp_path / video.file_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"irrelevant")

    whisper_extract = mocker.patch.object(media_processing_service.whisper_processor, "extract_audio")
    whisper_transcribe = mocker.patch.object(media_processing_service.whisper_processor, "transcribe_audio")

    media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    whisper_extract.assert_not_called()
    whisper_transcribe.assert_not_called()

    segments = pg_session.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).all()
    assert len(segments) == 1
    assert segments[0].text == "Uploaded subtitle text."
    assert segments[0].source == SubtitleSource.UPLOADED
    assert video.subtitle_source == SubtitleSource.UPLOADED


# ===========================================================================
# 8. Source precedence -- embedded subtitle skips Whisper entirely
# ===========================================================================

def test_embedded_subtitle_is_used_and_whisper_is_never_called(mocker, pg_session, tmp_path):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)  # subtitle_source defaults to NONE
    pg_session.commit()

    mocker.patch.object(media_processing_service.settings, "storage_root", str(tmp_path))
    source_path = tmp_path / video.file_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"fake source bytes")

    mocker.patch.object(media_processing_service, "probe_embedded_subtitle_stream_index", return_value=2)

    def _fake_extract(source, dest, stream_index):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("1\n00:00:00,000 --> 00:00:02,000\nEmbedded subtitle text.\n", encoding="utf-8")

    mocker.patch.object(media_processing_service, "extract_embedded_subtitle", side_effect=_fake_extract)

    whisper_extract = mocker.patch.object(media_processing_service.whisper_processor, "extract_audio")
    whisper_transcribe = mocker.patch.object(media_processing_service.whisper_processor, "transcribe_audio")

    media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    whisper_extract.assert_not_called()
    whisper_transcribe.assert_not_called()

    segments = pg_session.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).all()
    assert len(segments) == 1
    assert segments[0].text == "Embedded subtitle text."
    assert segments[0].source == SubtitleSource.EMBEDDED
    assert video.subtitle_source == SubtitleSource.EMBEDDED
    assert video.subtitle_path is not None
    assert (tmp_path / video.subtitle_path).exists()


# ===========================================================================
# 9. Source precedence -- a failed uploaded subtitle falls through to Whisper
# ===========================================================================

def test_missing_uploaded_subtitle_file_falls_back_to_whisper(mocker, pg_session, tmp_path):
    # subtitle_source says UPLOADED but the file itself is gone (e.g.
    # removed from disk out of band) -- must not crash or fail the whole
    # video, must fall through the rest of the precedence chain.
    user = _pg_make_user(pg_session)
    video = _pg_make_video(
        pg_session, user.id,
        subtitle_source=SubtitleSource.UPLOADED,
        subtitle_path=f"subtitles/{user.id}/missing.srt",
    )
    pg_session.commit()

    _mock_extraction(mocker, tmp_path, video)  # writes the real source file, but not the subtitle file
    mocker.patch.object(media_processing_service, "probe_embedded_subtitle_stream_index", return_value=None)
    mocker.patch.object(
        media_processing_service.whisper_processor, "transcribe_audio",
        return_value=[_whisper_segment(0.0, 1.0, "whisper fallback text")],
    )

    media_processing_service._generate_transcript(pg_session, video)
    pg_session.commit()

    segments = pg_session.query(TranscriptSegment).filter(TranscriptSegment.video_id == video.id).all()
    assert len(segments) == 1
    assert segments[0].text == "whisper fallback text"
    assert segments[0].source == SubtitleSource.WHISPER
    assert video.subtitle_source == SubtitleSource.WHISPER

    # The failed uploaded-subtitle read must have been logged, not silently
    # dropped -- see error_log_service.log_error's own contract.
    from app.models.error_log import ErrorLog
    error_logs = pg_session.query(ErrorLog).filter(ErrorLog.video_id == video.id).all()
    assert any(log.error_source == "subtitle_processing" for log in error_logs)
