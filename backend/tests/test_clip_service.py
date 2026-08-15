"""
test_clip_service.py

1. Shared helpers
2. Unit tests -- authorization (owner, shared, another user's private, admin)
3. Unit tests -- READY-only requirement
4. Unit tests -- first generation, safe filenames, output format
5. Unit tests -- cached reuse (file exists) / cache repair (file missing)
6. Unit tests -- persistence, selected_at
7. Unit tests -- GET streaming (auth, content-type, missing file)
8. Unit tests -- no Search Archive/saved state created
9. Unit tests -- failure cleanup (FFmpeg failure, persistence failure)
9b. Unit tests -- concurrent-create race recovery (2026-08-06 fix)
10. Unit tests -- ffmpeg_processor.generate_clip itself (missing binary,
    timeout) -- real filesystem, mocked subprocess, no real FFmpeg needed
11. Schema test -- no raw path ever exposed
12. Integration tests -- real FFmpeg (RUN_FFMPEG_INTEGRATION_TESTS)

match_resolver.resolve_clip_boundaries and ffmpeg_processor.generate_clip
are both patched via mocker.patch.object for most tests here -- this
module's own responsibility is authorization/cache/persistence/cleanup,
not scene-boundary math (covered by test_match_resolver.py) or real
FFmpeg behavior (covered by section 12, separately gated). Real files are
used on pytest's own tmp_path rather than mocking pathlib.Path.exists --
simpler and closer to real behavior for cache-hit/cache-miss/regeneration
scenarios specifically.
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SearchType, UserRole
from app.models.generated_clip import GeneratedClip
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.processing import ffmpeg_processor
from app.processing.ffmpeg_processor import ProcessingError
from app.schemas.clip import GeneratedClipOut
from app.services import clip_service, match_resolver

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
    return Video(**defaults)


def _make_query(**overrides) -> SearchQuery:
    defaults = dict(id=1, user_id=1, query_text="binary search tree", query_type=SearchType.EXACT_TEXT)
    defaults.update(overrides)
    return SearchQuery(**defaults)


def _make_result(video: Video, query: SearchQuery, **overrides) -> SearchResult:
    defaults = dict(
        id=1,
        query_id=query.id,
        video_id=video.id,
        transcript_segment_id=50,
        matched_start_time=100.0,
        matched_end_time=110.0,
        matched_text="binary search tree",
        confidence_score=0.9,
        rank_position=1,
        selected_at=None,
    )
    defaults.update(overrides)
    result = SearchResult(**defaults)
    result.video = video
    result.query = query
    result.clip = None
    return result


def _make_clip(result: SearchResult, video: Video, **overrides) -> GeneratedClip:
    defaults = dict(
        id=1,
        result_id=result.id,
        video_id=video.id,
        start_time=97.0,
        end_time=113.0,
        clip_path=f"clips/{video.id}/existing.mp4",
        clip_url="/api/clips/1",
    )
    defaults.update(overrides)
    return GeneratedClip(**defaults)


def _make_mock_db(result=None, clip_lookup=None):
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append

    def _flush():
        next_id = 1
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = next_id
            next_id = obj.id + 1

    mock_db.flush.side_effect = _flush
    mock_db.commit.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: None
    mock_db._added = added

    def _query(model):
        q = MagicMock()
        q.options.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        if model is SearchResult:
            q.first.return_value = result
        elif model is GeneratedClip:
            q.first.return_value = clip_lookup
        else:
            q.first.return_value = None
        return q

    mock_db.query.side_effect = _query
    return mock_db


def _make_settings(tmp_path, **overrides) -> SimpleNamespace:
    defaults = dict(
        storage_root=str(tmp_path),
        clip_generation_timeout_seconds=60,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _write_source_file(tmp_path, video: Video, content: bytes = b"fake source bytes") -> None:
    path = tmp_path / video.file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _default_instruction(video: Video, is_audio_only: bool = False) -> match_resolver.ClipInstruction:
    return match_resolver.ClipInstruction(
        video=video, start_time=97.0, end_time=113.0, duration=16.0, is_audio_only=is_audio_only,
    )


# ===========================================================================
# 2. Authorization
# ===========================================================================


def test_owner_can_generate_clip_for_own_private_video(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.reused is False
    assert clip_result.clip.video_id == video.id


def test_any_user_can_generate_clip_for_shared_video(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.SHARED)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, other_user, result.id)

    assert clip_result.clip.video_id == video.id


def test_another_users_private_result_returns_not_found(mocker, tmp_path):
    owner = _make_user(id=1)
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.ResultNotFoundError):
        clip_service.get_or_create_clip(db, other_user, result.id)


def test_admin_receives_no_hidden_bypass_for_private_video(mocker, tmp_path):
    owner = _make_user(id=1)
    admin = _make_user(id=99, username="admin", email="admin@example.com", role=UserRole.ADMIN)
    video = _make_video(id=1, owner_id=owner.id, visibility=MediaVisibility.PRIVATE)
    query = _make_query()
    result = _make_result(video, query)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.ResultNotFoundError):
        clip_service.get_or_create_clip(db, admin, result.id)


def test_missing_result_returns_not_found(mocker, tmp_path):
    user = _make_user(id=1)
    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=None)

    with pytest.raises(clip_service.ResultNotFoundError):
        clip_service.get_or_create_clip(db, user, 999)


# ===========================================================================
# 3. READY-only requirement
# ===========================================================================


def test_video_not_ready_raises(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, status=MediaStatus.PROCESSING)
    query = _make_query()
    result = _make_result(video, query)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.VideoNotReadyError):
        clip_service.get_or_create_clip(db, user, result.id)


# ===========================================================================
# 4. First generation, safe filenames, output format
# ===========================================================================


def test_first_generation_calls_match_resolver_and_ffmpeg_once(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    resolve_mock = mocker.patch.object(
        match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video)
    )
    generate_mock = mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    resolve_mock.assert_called_once()
    generate_mock.assert_called_once()
    assert clip_result.reused is False
    assert clip_result.clip.start_time == 97.0
    assert clip_result.clip.end_time == 113.0


def test_generated_filename_is_server_generated_uuid_under_video_id_folder(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=7, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch(
        "app.services.clip_service.uuid.uuid4",
        return_value=SimpleNamespace(hex="deadbeefcafe"),
    )
    generate_mock = mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.clip.clip_path == "clips/7/deadbeefcafe.mp4"
    # Never the client's original filename, never an absolute host path.
    assert "source.mp4" not in clip_result.clip.clip_path
    called_output_path = generate_mock.call_args[0][1]
    assert called_output_path.name == "deadbeefcafe.mp4"


def test_video_source_produces_mp4_with_is_audio_only_false(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="video/mp4")
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(
        match_resolver, "resolve_clip_boundaries",
        return_value=_default_instruction(video, is_audio_only=False),
    )
    generate_mock = mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.clip.clip_path.endswith(".mp4")
    assert generate_mock.call_args[0][4] is False  # is_audio_only positional arg


def test_audio_only_source_produces_mp3_with_is_audio_only_true(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="audio/mpeg", file_path="videos/1/source.mp3")
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(
        match_resolver, "resolve_clip_boundaries",
        return_value=_default_instruction(video, is_audio_only=True),
    )
    generate_mock = mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.clip.clip_path.endswith(".mp3")
    assert generate_mock.call_args[0][4] is True


def test_source_file_missing_raises(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    # Deliberately not writing the source file.

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.SourceFileMissingError):
        clip_service.get_or_create_clip(db, user, result.id)


# ===========================================================================
# 5. Cached reuse / cache repair
# ===========================================================================


def test_cached_clip_with_existing_file_is_reused_without_ffmpeg(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video, clip_path=f"clips/{video.id}/existing.mp4")
    result.clip = clip
    (tmp_path / clip.clip_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / clip.clip_path).write_bytes(b"already here")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    resolve_mock = mocker.patch.object(match_resolver, "resolve_clip_boundaries")
    generate_mock = mocker.patch.object(clip_service.ffmpeg_processor, "generate_clip")
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.reused is True
    assert clip_result.clip is clip
    resolve_mock.assert_not_called()
    generate_mock.assert_not_called()


def test_cached_clip_with_missing_file_regenerates_using_stored_boundaries(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    clip = _make_clip(result, video, clip_path=f"clips/{video.id}/gone.mp4", start_time=50.0, end_time=60.0)
    result.clip = clip
    # File deliberately not written -- the row exists but the file is gone.
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    resolve_mock = mocker.patch.object(match_resolver, "resolve_clip_boundaries")
    generate_mock = mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"regenerated"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.reused is False
    resolve_mock.assert_not_called()  # boundaries are NOT re-resolved
    generate_mock.assert_called_once()
    # Same stored boundaries reused, not recomputed
    assert generate_mock.call_args[0][2] == 50.0
    assert generate_mock.call_args[0][3] == 60.0
    # Same clip_path/row reused, no duplicate row
    assert clip_result.clip is clip
    assert clip_result.clip.clip_path == f"clips/{video.id}/gone.mp4"
    assert len(db._added) == 0


# ===========================================================================
# 6. Persistence, selected_at
# ===========================================================================


def test_generated_clip_persisted_with_correct_fields(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.clip.result_id == result.id
    assert clip_result.clip.video_id == video.id
    assert clip_result.clip.clip_url == f"/api/clips/{clip_result.clip.id}"
    assert clip_result.clip in db._added


def test_selected_at_set_only_once_on_first_successful_post(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, selected_at=None)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_service.get_or_create_clip(db, user, result.id)

    assert result.selected_at is not None


def test_selected_at_not_overwritten_on_repeated_post(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    original_timestamp = datetime.datetime(2026, 1, 1, 12, 0, 0)
    result = _make_result(video, query, selected_at=original_timestamp)
    clip = _make_clip(result, video, clip_path=f"clips/{video.id}/existing.mp4")
    result.clip = clip
    (tmp_path / clip.clip_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / clip.clip_path).write_bytes(b"already here")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=result)

    clip_service.get_or_create_clip(db, user, result.id)

    assert result.selected_at == original_timestamp


# ===========================================================================
# 7. GET streaming
# ===========================================================================


def test_get_clip_for_streaming_returns_path_and_content_type(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="video/mp4")
    clip = GeneratedClip(id=1, result_id=1, video_id=1, start_time=0.0, end_time=10.0,
                          clip_path=f"clips/{video.id}/x.mp4", clip_url="/api/clips/1")
    clip.video = video
    (tmp_path / clip.clip_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / clip.clip_path).write_bytes(b"bytes")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=clip)

    result_clip, abs_path, media_type = clip_service.get_clip_for_streaming(db, user, clip.id)

    assert result_clip is clip
    assert abs_path.exists()
    assert media_type == "video/mp4"


def test_get_clip_for_streaming_audio_content_type(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1, mime_type="audio/mpeg")
    clip = GeneratedClip(id=1, result_id=1, video_id=1, start_time=0.0, end_time=10.0,
                          clip_path=f"clips/{video.id}/x.mp3", clip_url="/api/clips/1")
    clip.video = video
    (tmp_path / clip.clip_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / clip.clip_path).write_bytes(b"bytes")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=clip)

    _, _, media_type = clip_service.get_clip_for_streaming(db, user, clip.id)

    assert media_type == "audio/mpeg"


def test_get_clip_for_streaming_unauthorized_returns_not_found(mocker, tmp_path):
    other_user = _make_user(id=2, username="other", email="other@example.com")
    video = _make_video(id=1, owner_id=1, visibility=MediaVisibility.PRIVATE)
    clip = GeneratedClip(id=1, result_id=1, video_id=1, start_time=0.0, end_time=10.0,
                          clip_path=f"clips/{video.id}/x.mp4", clip_url="/api/clips/1")
    clip.video = video

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=clip)

    with pytest.raises(clip_service.ClipNotFoundError):
        clip_service.get_clip_for_streaming(db, other_user, clip.id)


def test_get_clip_for_streaming_missing_clip_row_returns_not_found(mocker, tmp_path):
    user = _make_user(id=1)
    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=None)

    with pytest.raises(clip_service.ClipNotFoundError):
        clip_service.get_clip_for_streaming(db, user, 999)


def test_get_clip_for_streaming_missing_file_without_regeneration(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    clip = GeneratedClip(id=1, result_id=1, video_id=1, start_time=0.0, end_time=10.0,
                          clip_path=f"clips/{video.id}/gone.mp4", clip_url="/api/clips/1")
    clip.video = video
    # File deliberately not written.

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=clip)

    with pytest.raises(clip_service.MissingCachedFileError):
        clip_service.get_clip_for_streaming(db, user, clip.id)


def test_get_clip_for_streaming_never_touches_selected_at(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    clip = GeneratedClip(id=1, result_id=1, video_id=1, start_time=0.0, end_time=10.0,
                          clip_path=f"clips/{video.id}/x.mp4", clip_url="/api/clips/1")
    clip.video = video
    (tmp_path / clip.clip_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / clip.clip_path).write_bytes(b"bytes")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(clip_lookup=clip)

    clip_service.get_clip_for_streaming(db, user, clip.id)

    # get_clip_for_streaming has no access to a SearchResult at all --
    # structurally incapable of setting selected_at.
    db.commit.assert_not_called()


# ===========================================================================
# 8. No Search Archive / saved state created
# ===========================================================================


def test_generation_adds_only_the_generated_clip_row(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)

    clip_service.get_or_create_clip(db, user, result.id)

    # Only the GeneratedClip row is added -- get_or_create_clip never
    # creates a saved_results (bookmark) row; that is a separate, explicit
    # action handled by saved_result_service.py.
    assert len(db._added) == 1
    assert isinstance(db._added[0], GeneratedClip)


# ===========================================================================
# 9. Failure cleanup
# ===========================================================================


def test_ffmpeg_failure_does_not_persist_a_clip_row(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=ProcessingError("ffmpeg exploded"),
    )
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.ClipGenerationError):
        clip_service.get_or_create_clip(db, user, result.id)

    # No GeneratedClip row was persisted -- but error_log_service.log_error
    # (2026-08-08) does legitimately stage exactly one ErrorLog row on this
    # path, which is the behavior under test in
    # test_ffmpeg_failure_is_logged_then_reraised below, not a regression
    # here. Distinguish by type rather than asserting zero additions.
    assert not any(isinstance(obj, GeneratedClip) for obj in db._added)
    added_error_logs = [obj for obj in db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1


def test_persistence_failure_after_ffmpeg_success_deletes_file_and_rolls_back(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result)
    db.flush.side_effect = SQLAlchemyError("boom")

    with pytest.raises(SQLAlchemyError):
        clip_service.get_or_create_clip(db, user, result.id)

    db.rollback.assert_called_once()
    # The just-written file must not survive a failed flush.
    written_files = list((tmp_path / "clips" / str(video.id)).glob("*.mp4")) if (tmp_path / "clips" / str(video.id)).exists() else []
    assert written_files == []


def test_persistence_failure_on_reused_clip_does_not_delete_existing_file(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query, selected_at=None)
    clip = _make_clip(result, video, clip_path=f"clips/{video.id}/existing.mp4")
    result.clip = clip
    clip_abs_path = tmp_path / clip.clip_path
    clip_abs_path.parent.mkdir(parents=True, exist_ok=True)
    clip_abs_path.write_bytes(b"already here")

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    db = _make_mock_db(result=result)
    db.commit.side_effect = SQLAlchemyError("boom")

    with pytest.raises(SQLAlchemyError):
        clip_service.get_or_create_clip(db, user, result.id)

    db.rollback.assert_called_once()
    # Nothing new was written this call -- the pre-existing cached file
    # must be left alone.
    assert clip_abs_path.exists()


# ===========================================================================
# 9c. error_log_service coverage (2026-08-08) -- see test_search_error_logging.py
# for the dedicated error_log_service unit tests; these two just confirm the
# two call sites added to this module actually invoke it, without changing
# any of the existing exception behavior asserted above.
# ===========================================================================


def test_match_resolver_failure_is_logged_then_reraised(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(
        match_resolver, "resolve_clip_boundaries",
        side_effect=match_resolver.InvalidTimestampsError("no resolvable timestamps"),
    )
    db = _make_mock_db(result=result)

    with pytest.raises(match_resolver.InvalidTimestampsError):
        clip_service.get_or_create_clip(db, user, result.id)

    added_error_logs = [obj for obj in db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1
    # No GeneratedClip row staged alongside the log entry.
    assert len(db._added) == 1


def test_ffmpeg_failure_is_logged_then_reraised(mocker, tmp_path):
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=ProcessingError("ffmpeg exploded"),
    )
    db = _make_mock_db(result=result)

    with pytest.raises(clip_service.ClipGenerationError):
        clip_service.get_or_create_clip(db, user, result.id)

    added_error_logs = [obj for obj in db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1


# ===========================================================================
# 9b. Concurrent-create race recovery (2026-08-06 fix)
# ===========================================================================


def test_concurrent_create_race_returns_winners_clip_as_reused(mocker, tmp_path):
    # Two real concurrent POSTs for the same not-yet-cached result (e.g.
    # React 18 StrictMode's double-invoked mount effect, two open tabs, or
    # a fast double-click): both see result.clip is None, both resolve
    # boundaries and write a clip file, both try to insert a GeneratedClip
    # row. generated_clips.result_id is UNIQUE, so this request's flush()
    # raises IntegrityError -- recovery must roll back, discard this
    # request's own orphaned file, and return the concurrent winner's
    # already-committed row as reused=True instead of a 500.
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    winner_clip = _make_clip(
        result, video, id=99,
        clip_path=f"clips/{video.id}/winner.mp4",
        clip_url="/api/clips/99",
    )

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    # _load_result -> db.query(SearchResult) returns `result`; the
    # recovery re-query -> db.query(GeneratedClip) returns the winner --
    # each is queried exactly once on this code path, so the shared
    # _make_mock_db helper's fixed per-model return values are sufficient
    # (no need for a call-count-based side effect here).
    db = _make_mock_db(result=result, clip_lookup=winner_clip)
    db.flush.side_effect = IntegrityError("duplicate key", params=None, orig=Exception("dup"))

    clip_result = clip_service.get_or_create_clip(db, user, result.id)

    assert clip_result.reused is True
    assert clip_result.clip is winner_clip
    db.rollback.assert_called_once()
    # This request's own orphaned file must not survive; nothing else was
    # written to disk by this test, so the clips dir must end up empty.
    clips_dir = tmp_path / "clips" / str(video.id)
    written_files = list(clips_dir.glob("*.mp4")) if clips_dir.exists() else []
    assert written_files == []


def test_concurrent_create_race_reraises_when_no_winner_row_exists(mocker, tmp_path):
    # If the recovery re-query finds no GeneratedClip row at all, the
    # IntegrityError wasn't actually the expected race (e.g. a genuine
    # FK/constraint problem) -- it must not be silently swallowed.
    user = _make_user(id=1)
    video = _make_video(id=1, owner_id=1)
    query = _make_query()
    result = _make_result(video, query)
    _write_source_file(tmp_path, video)

    mocker.patch.object(clip_service, "get_settings", return_value=_make_settings(tmp_path))
    mocker.patch.object(match_resolver, "resolve_clip_boundaries", return_value=_default_instruction(video))
    mocker.patch.object(
        clip_service.ffmpeg_processor, "generate_clip",
        side_effect=lambda src, out, *a, **kw: out.write_bytes(b"dummy-clip"),
    )
    db = _make_mock_db(result=result, clip_lookup=None)
    db.flush.side_effect = IntegrityError("duplicate key", params=None, orig=Exception("dup"))

    with pytest.raises(IntegrityError):
        clip_service.get_or_create_clip(db, user, result.id)

    db.rollback.assert_called_once()


# ===========================================================================
# 10. ffmpeg_processor.generate_clip itself (missing binary, timeout)
# ===========================================================================


def test_generate_clip_cleans_up_on_missing_binary(mocker, tmp_path):
    fake_settings = SimpleNamespace(
        ffmpeg_binary="definitely-not-a-real-ffmpeg-binary",
        ffprobe_binary="ffprobe",
        ffmpeg_timeout_seconds=5,
    )
    mocker.patch.object(ffmpeg_processor, "settings", fake_settings)
    output_path = tmp_path / "out.mp4"

    with pytest.raises(ProcessingError):
        ffmpeg_processor.generate_clip(tmp_path / "in.mp4", output_path, 0.0, 5.0, False, timeout_seconds=5)

    assert not output_path.exists()


def test_generate_clip_cleans_up_on_timeout(mocker, tmp_path):
    fake_settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe", ffmpeg_timeout_seconds=5)
    mocker.patch.object(ffmpeg_processor, "settings", fake_settings)
    output_path = tmp_path / "out.mp4"
    output_path.write_bytes(b"partial-garbage")  # simulate a partial write before the timeout fires

    mocker.patch.object(
        ffmpeg_processor.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5),
    )

    with pytest.raises(ProcessingError):
        ffmpeg_processor.generate_clip(tmp_path / "in.mp4", output_path, 0.0, 5.0, False, timeout_seconds=5)

    assert not output_path.exists()


def test_generate_clip_uses_argument_array_never_shell(mocker, tmp_path):
    fake_settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe", ffmpeg_timeout_seconds=5)
    mocker.patch.object(ffmpeg_processor, "settings", fake_settings)
    output_path = tmp_path / "out.mp4"

    def _fake_run(command, **kwargs):
        assert isinstance(command, list)
        assert kwargs.get("shell", False) is False
        output_path.write_bytes(b"ok")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=_fake_run)

    ffmpeg_processor.generate_clip(tmp_path / "in.mp4", output_path, 10.0, 15.0, False, timeout_seconds=5)

    assert output_path.exists()


def test_generate_clip_audio_only_uses_mp3_codec_args(mocker, tmp_path):
    fake_settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe", ffmpeg_timeout_seconds=5)
    mocker.patch.object(ffmpeg_processor, "settings", fake_settings)
    output_path = tmp_path / "out.mp3"
    captured = {}

    def _fake_run(command, **kwargs):
        captured["command"] = command
        output_path.write_bytes(b"ok")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=_fake_run)

    ffmpeg_processor.generate_clip(tmp_path / "in.mp3", output_path, 10.0, 15.0, True, timeout_seconds=5)

    assert "libmp3lame" in captured["command"]
    assert "-c:v" not in captured["command"]


def test_generate_clip_video_uses_h264_aac_faststart(mocker, tmp_path):
    fake_settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe", ffmpeg_timeout_seconds=5)
    mocker.patch.object(ffmpeg_processor, "settings", fake_settings)
    output_path = tmp_path / "out.mp4"
    captured = {}

    def _fake_run(command, **kwargs):
        captured["command"] = command
        output_path.write_bytes(b"ok")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    mocker.patch.object(ffmpeg_processor.subprocess, "run", side_effect=_fake_run)

    ffmpeg_processor.generate_clip(tmp_path / "in.mp4", output_path, 10.0, 15.0, False, timeout_seconds=5)

    command = captured["command"]
    assert "libx264" in command
    assert "aac" in command
    assert "+faststart" in command


# ===========================================================================
# 11. Schema -- no raw path ever exposed
# ===========================================================================


def test_generated_clip_out_never_exposes_a_raw_path():
    assert "clip_path" not in GeneratedClipOut.model_fields
    assert "file_path" not in GeneratedClipOut.model_fields
    assert "clip_stream_url" in GeneratedClipOut.model_fields


# ===========================================================================
# 12. Real-FFmpeg integration tests (separately gated)
# ===========================================================================

RUN_FFMPEG_INTEGRATION_TESTS = os.environ.get("RUN_FFMPEG_INTEGRATION_TESTS") == "1"


def _ffmpeg_available() -> bool:
    # Deliberately reads the raw env var (same convention as
    # TEST_DATABASE_URL above) rather than calling get_settings() --
    # instantiating Settings() requires DATABASE_URL/JWT_SECRET_KEY to be
    # configured, which this skip check must not depend on: it needs to
    # work even at test-collection time, before any test has a reason to
    # need a real .env.
    binary = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    return shutil.which(binary) is not None


@pytest.mark.skipif(
    not RUN_FFMPEG_INTEGRATION_TESTS, reason="RUN_FFMPEG_INTEGRATION_TESTS is not set to 1"
)
@pytest.mark.skipif(not _ffmpeg_available(), reason="Configured FFmpeg binary not found on PATH")
class TestRealFfmpegClipGeneration:
    @pytest.fixture
    def tiny_source_video(self, tmp_path):
        # A short, real, silent test video generated with ffmpeg's own
        # lavfi test source -- deterministic, no external fixture file
        # needed, cleaned up automatically by tmp_path.
        source = tmp_path / "tiny_source.mp4"
        subprocess.run(
            [
                shutil.which("ffmpeg"), "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=3",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", "3", "-c:v", "libx264", "-c:a", "aac",
                str(source),
            ],
            check=True, capture_output=True,
        )
        return source

    def test_real_video_clip_generation(self, tiny_source_video, tmp_path):
        output_path = tmp_path / "clip.mp4"
        ffmpeg_processor.generate_clip(tiny_source_video, output_path, 0.5, 2.0, False, timeout_seconds=30)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        probe = subprocess.run(
            [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            check=True, capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip())
        assert duration == pytest.approx(1.5, abs=0.5)

    def test_real_audio_clip_generation(self, tiny_source_video, tmp_path):
        output_path = tmp_path / "clip.mp3"
        ffmpeg_processor.generate_clip(tiny_source_video, output_path, 0.0, 1.5, True, timeout_seconds=30)

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        probe = subprocess.run(
            [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            check=True, capture_output=True, text=True,
        )
        duration = float(probe.stdout.strip())
        assert duration == pytest.approx(1.5, abs=0.5)
