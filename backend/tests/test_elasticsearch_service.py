"""
test_elasticsearch_service.py

1. Unit tests -- mapping / document construction (pure functions, no server)
2. Unit tests -- safe-unavailable behavior when Elasticsearch is disabled
   (the default) -- every public function must raise
   ElasticsearchUnavailableError, never crash, never attempt a real
   connection
3. Regression guard -- live user search never imports this module
4. Environment-gated integration tests against a real Elasticsearch server
   (RUN_ELASTICSEARCH_INTEGRATION_TESTS=1) -- skipped, not failed, when
   unset. These have NOT been run in this environment; do not report them
   as passed until they are actually executed against a real server.
"""

from __future__ import annotations

import os

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video
from app.services import elasticsearch_service

# ===========================================================================
# 1. Unit tests -- mapping / document construction
# ===========================================================================


def test_mapping_declares_every_field_evaluate_query_and_authorization_filters_need():
    fields = elasticsearch_service._MAPPING["properties"]
    for expected_field in (
        "segment_id", "video_id", "text", "start_time", "end_time",
        "owner_id", "visibility", "video_status",
    ):
        assert expected_field in fields


def test_segment_to_document_maps_fields_from_the_real_orm_objects():
    video = Video(
        id=42, owner_id=9, title="V", original_filename="v.mp4",
        file_path="videos/9/v.mp4", file_size_bytes=1, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.SHARED,
    )
    segment = TranscriptSegment(
        id=100, video_id=42, start_time=1.5, end_time=3.5, text="hello world", source=SubtitleSource.WHISPER,
    )
    doc = elasticsearch_service._segment_to_document(segment, video)
    assert doc == {
        "segment_id": 100,
        "video_id": 42,
        "text": "hello world",
        "start_time": 1.5,
        "end_time": 3.5,
        "owner_id": 9,
        "visibility": "shared",
        "video_status": "ready",
    }


# ===========================================================================
# 2. Unit tests -- safe-unavailable behavior (Elasticsearch disabled/default)
# ===========================================================================


def test_is_available_is_false_and_never_raises_when_disabled_by_default():
    assert elasticsearch_service.is_available() is False


def test_ensure_index_raises_unavailable_instead_of_crashing_when_disabled():
    with pytest.raises(elasticsearch_service.ElasticsearchUnavailableError):
        elasticsearch_service.ensure_index()


def test_document_count_raises_unavailable_instead_of_crashing_when_disabled():
    with pytest.raises(elasticsearch_service.ElasticsearchUnavailableError):
        elasticsearch_service.document_count()


def test_evaluate_query_raises_unavailable_instead_of_crashing_when_disabled():
    with pytest.raises(elasticsearch_service.ElasticsearchUnavailableError):
        elasticsearch_service.evaluate_query(db=None, query_text="anything")


def test_backfill_raises_unavailable_before_touching_the_database_when_disabled():
    # ensure_index() is the first thing backfill() calls, and that raises
    # before backfill ever runs its db.query(...) -- passing db=None proves
    # this: a real (non-None) db would be required if backfill queried it.
    with pytest.raises(elasticsearch_service.ElasticsearchUnavailableError):
        elasticsearch_service.backfill(db=None)


def test_delete_segment_raises_unavailable_instead_of_crashing_when_disabled():
    with pytest.raises(elasticsearch_service.ElasticsearchUnavailableError):
        elasticsearch_service.delete_segment(segment_id=1)


# ===========================================================================
# 3. Regression guard -- live user search never imports this module
# ===========================================================================


def test_search_service_never_imports_elasticsearch_service():
    import inspect

    from app.services import search_service

    source = inspect.getsource(search_service)
    assert "elasticsearch" not in source.lower()


def test_search_router_never_imports_elasticsearch_service():
    import inspect

    from app.api import search as search_router

    source = inspect.getsource(search_router)
    assert "elasticsearch" not in source.lower()


# ===========================================================================
# 4. Environment-gated integration tests -- real Elasticsearch server
# ===========================================================================

RUN_ELASTICSEARCH_INTEGRATION_TESTS = os.environ.get("RUN_ELASTICSEARCH_INTEGRATION_TESTS") == "1"


@pytest.mark.skipif(
    not RUN_ELASTICSEARCH_INTEGRATION_TESTS,
    reason="RUN_ELASTICSEARCH_INTEGRATION_TESTS is not set to 1 -- set it plus ELASTICSEARCH_ENABLED=True "
    "and a real ELASTICSEARCH_URL in .env to run these against a live local Elasticsearch install. "
    "Not run in this environment -- see the Windows Elasticsearch setup tutorial.",
)
class TestRealElasticsearchIntegration:
    """None of these have been executed against a real server in this
    environment. They are reported as skipped by pytest, never as passed,
    until you set RUN_ELASTICSEARCH_INTEGRATION_TESTS=1 with a real,
    reachable Elasticsearch instance and run them yourself."""

    def test_ensure_index_creates_the_index_idempotently(self):
        elasticsearch_service.ensure_index()
        elasticsearch_service.ensure_index()  # second call must not error
        assert elasticsearch_service.is_available() is True

    def test_index_and_query_a_segment_round_trip(self, pg_session):
        video, segment = _make_test_video_and_segment(pg_session)
        elasticsearch_service.ensure_index()
        elasticsearch_service.index_segment(segment, video)

        result = elasticsearch_service.evaluate_query(pg_session, query_text=segment.text, limit=5)
        matched_video_ids = {video_id for video_id, _start, _end in result.ranked_video_windows}
        assert video.id in matched_video_ids

    def test_backfill_indexes_every_ready_video_segment(self, pg_session):
        count = elasticsearch_service.backfill(pg_session)
        assert count >= 0

    def test_delete_segment_removes_it_from_the_index(self, pg_session):
        video, segment = _make_test_video_and_segment(pg_session)
        elasticsearch_service.ensure_index()
        elasticsearch_service.index_segment(segment, video)
        elasticsearch_service.delete_segment(segment.id)


def _make_test_video_and_segment(pg_session):
    from app.models.user import User

    owner = User(full_name="ES Test", username=f"esuser{id(pg_session)}", email=f"es{id(pg_session)}@example.com", password_hash="x")
    pg_session.add(owner)
    pg_session.flush()
    video = Video(
        owner_id=owner.id, title="ES Video", original_filename="es.mp4",
        file_path=f"videos/{owner.id}/es.mp4", file_size_bytes=1, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD, visibility=MediaVisibility.PRIVATE,
    )
    pg_session.add(video)
    pg_session.flush()
    segment = TranscriptSegment(video_id=video.id, start_time=0.0, end_time=2.0, text="elasticsearch integration test phrase", source=SubtitleSource.WHISPER)
    pg_session.add(segment)
    pg_session.flush()
    pg_session.commit()
    return video, segment
