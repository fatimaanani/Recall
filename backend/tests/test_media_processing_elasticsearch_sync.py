"""
test_media_processing_elasticsearch_sync.py

Elasticsearch is disabled by default in every environment that hasn't
explicitly set ELASTICSEARCH_ENABLED=True (see app/config.py) -- which
means the real, non-mocked behavior of every function tested here, in
this environment and in any CI environment without a live ES server, is
"raise ElasticsearchUnavailableError immediately, caught and swallowed by
the caller." These tests exercise exactly that real path against a real
Postgres database (no mocking of elasticsearch_service itself needed),
proving the two lifecycle sync points -- `_sync_elasticsearch_reindex`
(video reprocessing/transcription) and `purge_video`'s post-delete
cleanup -- never raise and never affect real data, which is the actual
safety contract that matters ("Elasticsearch failures do not affect live
user search/processing/deletion").

1. Shared pg_* helpers
2. _sync_elasticsearch_reindex never raises, never blocks
3. purge_video's Elasticsearch cleanup never raises, deletion still succeeds
"""

from __future__ import annotations

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.services import media_processing_service, video_service

# ===========================================================================
# 1. Shared pg_* helpers
# ===========================================================================


def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(full_name="ES Sync User", username=f"essyncuser{id(overrides)}", email=f"essync{id(overrides)}@example.com", password_hash="x")
    defaults.update(overrides)
    user = User(**defaults)
    pg_session.add(user)
    pg_session.flush()
    return user


def _pg_make_video(pg_session, owner_id, **overrides) -> Video:
    defaults = dict(
        owner_id=owner_id, title="ES Sync Video", original_filename="v.mp4",
        file_path=f"videos/{owner_id}/v.mp4", file_size_bytes=1024, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD, visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    pg_session.add(video)
    pg_session.flush()
    return video


def _pg_make_segment(pg_session, video_id, **overrides) -> TranscriptSegment:
    defaults = dict(video_id=video_id, start_time=0.0, end_time=2.0, text="segment text", source=SubtitleSource.WHISPER)
    defaults.update(overrides)
    segment = TranscriptSegment(**defaults)
    pg_session.add(segment)
    pg_session.flush()
    return segment


# ===========================================================================
# 2. _sync_elasticsearch_reindex
# ===========================================================================


def test_sync_reindex_never_raises_when_elasticsearch_is_disabled(pg_session):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    segment = _pg_make_segment(pg_session, video.id)
    pg_session.commit()

    # Must not raise -- this is called from inside process_video's happy
    # path, right after the whisper stage commits.
    media_processing_service._sync_elasticsearch_reindex(pg_session, video, removed_segment_ids=[])

    # Real data is completely unaffected -- the segment created above is
    # still there, untouched.
    assert pg_session.query(TranscriptSegment).filter(TranscriptSegment.id == segment.id).count() == 1


def test_sync_reindex_never_raises_with_removed_segment_ids_present(pg_session):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    pg_session.commit()

    # Simulates a reprocess: some old (now-deleted) segment ids to clean
    # up from the evaluation index, even though nothing in Postgres
    # references them anymore.
    media_processing_service._sync_elasticsearch_reindex(pg_session, video, removed_segment_ids=[999999, 999998])


# ===========================================================================
# 3. purge_video's Elasticsearch cleanup
# ===========================================================================


def test_purge_video_deletes_the_video_even_when_it_has_transcript_segments(pg_session):
    user = _pg_make_user(pg_session)
    video = _pg_make_video(pg_session, user.id)
    _pg_make_segment(pg_session, video.id)
    pg_session.commit()
    video_id = video.id

    # Must not raise -- Elasticsearch cleanup after the real delete has
    # already committed must never surface as a failure to the caller.
    video_service.purge_video(pg_session, video)

    assert pg_session.query(Video).filter(Video.id == video_id).count() == 0
    # Cascade removed the segment too (existing FK behavior).
    assert pg_session.query(TranscriptSegment).filter(TranscriptSegment.video_id == video_id).count() == 0
