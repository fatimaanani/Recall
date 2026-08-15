"""
test_upload_details_media.py

Unit tests for two Upload Details backend prerequisites: original-media
streaming (video_service.get_video_stream_path) and read-only transcript
retrieval (video_service.get_transcript_segments).
Both simply delegate authorization to the existing video_service.get_video
(owner-or-shared, else VideoNotFoundError) -- these tests confirm that
delegation actually happens, plus each function's own additional behavior
(missing-file detection for streaming, ordering/shape for transcript).

Same style as test_clip_service.py: real objects, a small hand-rolled mock
Session (mocker.patch.object for settings, MagicMock for db.query chains),
real files on pytest's own tmp_path rather than mocking pathlib.Path.exists.

1. Shared helpers
2. Streaming -- authorization (owner, shared, another user's private, nonexistent)
3. Streaming -- missing source file
4. Streaming -- media type passthrough (video, audio)
5. Transcript -- authorization (owner, shared, another user's private, nonexistent)
6. Transcript -- ordering, empty list, schema shape
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, UserRole
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.schemas.video import TranscriptSegmentOut
from app.services import video_service

# ===========================================================================
# 1. Shared helpers
# ===========================================================================


def _make_user(**overrides) -> User:
    defaults = dict(
        id=1,
        full_name="Test User",
        username="testuser",
        email="test@example.com",
        password_hash="not-a-real-hash",
        role=UserRole.USER,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1,
        owner_id=1,
        title="Test video",
        original_filename="test.mp4",
        file_path="videos/1/source.mp4",
        file_size_bytes=1024,
        mime_type="video/mp4",
        duration_seconds=600.0,
        status=MediaStatus.READY,
        source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    video.category_links = []
    return video


def _make_segment(**overrides) -> TranscriptSegment:
    defaults = dict(id=1, video_id=1, start_time=0.0, end_time=5.0, text="Hello world")
    defaults.update(overrides)
    return TranscriptSegment(**defaults)


def _make_settings(tmp_path, **overrides) -> SimpleNamespace:
    defaults = dict(storage_root=str(tmp_path))
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _write_source_file(tmp_path, video: Video, content: bytes = b"fake source bytes") -> None:
    path = tmp_path / video.file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_mock_db(video=None, segments=None):
    mock_db = MagicMock()
    # One query mock per model, memoized -- so a test can call
    # db.query.side_effect(Model) again afterward and get back the exact
    # same mock the code under test used, not a fresh untouched one.
    query_mocks: dict = {}

    def _query(model):
        if model in query_mocks:
            return query_mocks[model]
        q = MagicMock()
        q.options.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        if model is Video:
            q.first.return_value = video
        elif model is TranscriptSegment:
            q.all.return_value = segments if segments is not None else []
        else:
            q.first.return_value = None
            q.all.return_value = []
        query_mocks[model] = q
        return q

    mock_db.query.side_effect = _query
    return mock_db


# ===========================================================================
# 2. Streaming -- authorization
# ===========================================================================


def test_owner_can_stream_own_private_upload(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.PRIVATE)
    _write_source_file(tmp_path, video)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    result_video, abs_path, media_type = video_service.get_video_stream_path(db, user, video.id)

    assert result_video is video
    assert abs_path.exists()
    assert media_type == "video/mp4"


def test_any_authorized_user_can_stream_shared_upload(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.SHARED)
    _write_source_file(tmp_path, video)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    _result_video, abs_path, _media_type = video_service.get_video_stream_path(db, other_user, video.id)

    assert abs_path.exists()


def test_another_users_private_upload_returns_not_found_for_streaming(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    _write_source_file(tmp_path, video)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    with pytest.raises(video_service.VideoNotFoundError):
        video_service.get_video_stream_path(db, other_user, video.id)


def test_nonexistent_video_returns_not_found_for_streaming(mocker, tmp_path):
    user = _make_user(id=1)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=None)

    with pytest.raises(video_service.VideoNotFoundError):
        video_service.get_video_stream_path(db, user, 999)


# ===========================================================================
# 3. Streaming -- missing source file
# ===========================================================================


def test_missing_source_file_raises_source_file_missing_error(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    # Deliberately not writing the source file.
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    with pytest.raises(video_service.SourceFileMissingError):
        video_service.get_video_stream_path(db, user, video.id)


# ===========================================================================
# 4. Streaming -- media type passthrough
# ===========================================================================


def test_streaming_returns_real_stored_mime_type_for_video(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="video/mp4")
    _write_source_file(tmp_path, video)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    _video, _abs_path, media_type = video_service.get_video_stream_path(db, user, video.id)

    assert media_type == "video/mp4"


def test_streaming_returns_real_stored_mime_type_for_audio(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="audio/mpeg", file_path="videos/1/source.mp3")
    _write_source_file(tmp_path, video)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video)

    _video, _abs_path, media_type = video_service.get_video_stream_path(db, user, video.id)

    assert media_type == "audio/mpeg"


# ===========================================================================
# 5. Transcript -- authorization
# ===========================================================================


def test_owner_can_fetch_own_transcript(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.PRIVATE)
    segments = [_make_segment(id=1, start_time=0.0), _make_segment(id=2, start_time=5.0)]
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video, segments=segments)

    result = video_service.get_transcript_segments(db, user, video.id)

    assert result == segments


def test_shared_video_transcript_is_accessible(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.SHARED)
    segments = [_make_segment(id=1)]
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video, segments=segments)

    result = video_service.get_transcript_segments(db, other_user, video.id)

    assert result == segments


def test_another_users_private_transcript_returns_not_found(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video, segments=[_make_segment()])

    with pytest.raises(video_service.VideoNotFoundError):
        video_service.get_transcript_segments(db, other_user, video.id)


def test_nonexistent_video_returns_not_found_for_transcript(mocker, tmp_path):
    user = _make_user(id=1)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=None)

    with pytest.raises(video_service.VideoNotFoundError):
        video_service.get_transcript_segments(db, user, 999)


# ===========================================================================
# 6. Transcript -- ordering, empty list, schema shape
# ===========================================================================


def test_transcript_query_orders_by_start_time_ascending(mocker, tmp_path):
    # The mock's order_by() is a no-op passthrough (it just returns the
    # same query mock), so this test asserts the *call* happened with the
    # right column rather than re-sorting mock data -- real ascending
    # ordering is provided by PostgreSQL itself in the real database (this
    # is a unit test, not a database-integration test).
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    segments = [_make_segment(id=1, start_time=0.0), _make_segment(id=2, start_time=5.0)]
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video, segments=segments)

    video_service.get_transcript_segments(db, user, video.id)

    transcript_query_mock = db.query.side_effect(TranscriptSegment)
    transcript_query_mock.order_by.assert_called_once()
    order_by_arg = str(transcript_query_mock.order_by.call_args[0][0])
    assert "start_time" in order_by_arg


def test_empty_transcript_returns_empty_list(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    mocker.patch.object(video_service, "settings", _make_settings(tmp_path))
    db = _make_mock_db(video=video, segments=[])

    result = video_service.get_transcript_segments(db, user, video.id)

    assert result == []


def test_transcript_segment_out_contains_only_intended_fields():
    assert set(TranscriptSegmentOut.model_fields.keys()) == {"id", "start_time", "end_time", "text"}
    # Never exposes embedding vectors or the raw search_vector column.
    assert "embedding" not in TranscriptSegmentOut.model_fields
    assert "search_vector" not in TranscriptSegmentOut.model_fields


def test_transcript_segment_out_serializes_real_segment():
    segment = _make_segment(id=5, start_time=12.5, end_time=18.0, text="binary search tree")
    out = TranscriptSegmentOut.model_validate(segment)

    assert out.id == 5
    assert out.start_time == 12.5
    assert out.end_time == 18.0
    assert out.text == "binary search tree"
