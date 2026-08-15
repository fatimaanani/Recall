"""
test_video_service_subtitle_upload.py

Unit tests for the subtitle-upload-specific behavior in
video_service.save_upload -- validating, saving, and recording an
optional SRT/VTT file alongside a video upload. Mocked DB session (no
Postgres needed), real filesystem via tmp_path, real
subtitle_validation.py (not mocked) so these prove the actual
accept/reject behavior, not a stubbed-out approximation.

This file covers only the subtitle-specific behavior; it is not a full
retrofit of coverage for the rest of the upload flow
(checksum/quota/duplicate-detection).

1. Shared helpers
2. Successful subtitle upload alongside a video
3. No subtitle provided -- unchanged existing behavior
4. Invalid subtitle rejects the whole upload, cleans up nothing orphaned
5. purge_video removes the subtitle file too
"""

from __future__ import annotations

import asyncio
import io
import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource, UserRole
from app.models.user import User
from app.models.video import Video
from app.services import video_service
from app.utils.subtitle_validation import InvalidSubtitleFileError

_VALID_SRT = b"1\n00:00:00,000 --> 00:00:02,000\nHello there.\n"

# Minimal valid MP4 signature (ISO base media "ftyp" box) -- passes
# file_validation.validate_upload's real magic-byte check.
_VALID_MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8


class _FakeUploadFile:
    """Duck-typed stand-in for fastapi.UploadFile -- async read/seek/close,
    backed by an in-memory BytesIO. No real UploadFile instantiation
    needed (that requires a real Starlette request context)."""

    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._buffer = io.BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size if size != -1 else None)

    async def seek(self, offset: int) -> None:
        self._buffer.seek(offset)

    async def close(self) -> None:
        pass


def _make_user(**overrides) -> User:
    defaults = dict(
        id=1, full_name="Test User", username="testuser", email="test@example.com",
        password_hash="x", role=UserRole.USER, storage_limit_bytes=10 * 1024 * 1024 * 1024,
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_mock_db():
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append
    mock_db.commit.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", obj.id or 1)
    mock_db._added = added

    def _query(model):
        q = MagicMock()
        q.filter.return_value = q
        q.scalar.return_value = 0  # used storage bytes
        q.first.return_value = None  # no duplicate found
        return q

    mock_db.query.side_effect = _query
    return mock_db


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# 2. Successful subtitle upload alongside a video
# ===========================================================================

def test_save_upload_with_valid_subtitle_persists_uploaded_source(mocker, tmp_path):
    mocker.patch.object(video_service, "settings", SimpleNamespace(
        storage_root=str(tmp_path),
        max_upload_size_bytes=5 * 1024 * 1024 * 1024,
        max_subtitle_upload_size_bytes=2 * 1024 * 1024,
    ))
    user = _make_user()
    db = _make_mock_db()
    video_file = _FakeUploadFile("movie.mp4", _VALID_MP4_HEAD)
    subtitle_file = _FakeUploadFile("movie.srt", _VALID_SRT)

    video = _run(video_service.save_upload(db, user, video_file, "My Movie", subtitle_file))

    assert video.subtitle_source == SubtitleSource.UPLOADED
    assert video.has_subtitles is True
    assert video.subtitle_path is not None
    assert video.subtitle_path.startswith(f"subtitles/{user.id}/")
    saved_path = pathlib.Path(tmp_path) / video.subtitle_path
    assert saved_path.exists()
    assert saved_path.read_bytes() == _VALID_SRT


# ===========================================================================
# 3. No subtitle provided -- unchanged existing behavior
# ===========================================================================

def test_save_upload_without_subtitle_defaults_to_none_source(mocker, tmp_path):
    mocker.patch.object(video_service, "settings", SimpleNamespace(
        storage_root=str(tmp_path),
        max_upload_size_bytes=5 * 1024 * 1024 * 1024,
        max_subtitle_upload_size_bytes=2 * 1024 * 1024,
    ))
    user = _make_user()
    db = _make_mock_db()
    video_file = _FakeUploadFile("movie.mp4", _VALID_MP4_HEAD)

    video = _run(video_service.save_upload(db, user, video_file, "My Movie"))

    assert video.subtitle_source == SubtitleSource.NONE
    assert video.has_subtitles is False
    assert video.subtitle_path is None


# ===========================================================================
# 4. Invalid subtitle rejects the whole upload
# ===========================================================================

def test_save_upload_with_invalid_subtitle_raises_before_writing_video_file(mocker, tmp_path):
    mocker.patch.object(video_service, "settings", SimpleNamespace(
        storage_root=str(tmp_path),
        max_upload_size_bytes=5 * 1024 * 1024 * 1024,
        max_subtitle_upload_size_bytes=2 * 1024 * 1024,
    ))
    user = _make_user()
    db = _make_mock_db()
    video_file = _FakeUploadFile("movie.mp4", _VALID_MP4_HEAD)
    bad_subtitle = _FakeUploadFile("notes.txt", b"just some text, not a real subtitle file")

    raised = False
    try:
        _run(video_service.save_upload(db, user, video_file, "My Movie", bad_subtitle))
    except InvalidSubtitleFileError:
        raised = True
    assert raised

    # Nothing left behind under storage_root -- the video file was never
    # written, since subtitle validation runs before any disk I/O.
    videos_dir = pathlib.Path(tmp_path) / "videos"
    written_files = list(videos_dir.rglob("*")) if videos_dir.exists() else []
    assert written_files == []
    db.add.assert_not_called()


# ===========================================================================
# 5. purge_video removes the subtitle file too
# ===========================================================================

def test_purge_video_removes_subtitle_file(mocker, tmp_path):
    mocker.patch.object(video_service, "settings", SimpleNamespace(storage_root=str(tmp_path)))
    mocker.patch.object(video_service.elasticsearch_service, "delete_segment")

    subtitle_rel_path = "subtitles/1/captions.srt"
    subtitle_abs_path = pathlib.Path(tmp_path) / subtitle_rel_path
    subtitle_abs_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_abs_path.write_bytes(_VALID_SRT)

    video = Video(
        id=1, owner_id=1, title="t", original_filename="movie.mp4",
        file_path="videos/1/movie.mp4", file_size_bytes=10, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE, subtitle_path=subtitle_rel_path,
        subtitle_source=SubtitleSource.UPLOADED, has_subtitles=True,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []  # no transcript segments
    db.commit.side_effect = lambda: None

    video_service.purge_video(db, video)

    assert not subtitle_abs_path.exists()
