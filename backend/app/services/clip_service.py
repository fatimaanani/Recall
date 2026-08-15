"""Handles authorization, cache reuse/repair, FFmpeg orchestration, and cleanup for generated scene clips; boundary math lives in match_resolver.py."""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import uuid

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.enums import MediaStatus, MediaVisibility
from app.models.generated_clip import GeneratedClip
from app.models.search_result import SearchResult
from app.models.user import User
from app.models.video import Video
from app.processing import ffmpeg_processor
from app.processing.ffmpeg_processor import ProcessingError
from app.services import error_log_service, match_resolver


class ResultNotFoundError(Exception):
    """No such SearchResult, or its video isn't accessible -- same error either way so private data is never confirmed to exist."""


class ClipNotFoundError(Exception):
    """No such GeneratedClip, or its video isn't accessible to this caller."""


class VideoNotReadyError(Exception):
    pass


class SourceFileMissingError(Exception):
    """The original uploaded file is gone from disk -- a data-integrity
    problem, not something the caller did wrong."""


class ClipGenerationError(Exception):
    """FFmpeg itself failed or timed out."""


class MissingCachedFileError(Exception):
    """GET found a GeneratedClip row, but its file is missing and GET is
    not a regeneration context (only POST repairs a missing file)."""


@dataclasses.dataclass
class ClipResult:
    clip: GeneratedClip
    video: Video
    result: SearchResult
    reused: bool


def _can_access_video(user: User, video: Video) -> bool:
    return video.owner_id == user.id or video.visibility == MediaVisibility.SHARED


def _load_result(db: Session, result_id: int) -> SearchResult | None:
    return (
        db.query(SearchResult)
        .options(
            joinedload(SearchResult.video),
            joinedload(SearchResult.query),
            joinedload(SearchResult.clip),
        )
        .filter(SearchResult.id == result_id)
        .first()
    )


def _clip_abs_path(clip_path: str) -> pathlib.Path:
    settings = get_settings()
    return pathlib.Path(settings.storage_root) / clip_path


def _write_clip_file(video: Video, start_time: float, end_time: float, abs_path: pathlib.Path, is_audio_only: bool) -> None:
    settings = get_settings()
    source_path = pathlib.Path(settings.storage_root) / video.file_path
    if not source_path.exists():
        raise SourceFileMissingError("The source media file for this video is missing.")

    try:
        ffmpeg_processor.generate_clip(
            source_path, abs_path, start_time, end_time, is_audio_only,
            timeout_seconds=settings.clip_generation_timeout_seconds,
        )
    except ProcessingError as exc:
        raise ClipGenerationError(str(exc)) from exc


# Entry point: POST /api/results/{result_id}/clip
def get_or_create_clip(db: Session, user: User, result_id: int) -> ClipResult:
    result = _load_result(db, result_id)
    if result is None:
        raise ResultNotFoundError()

    video = result.video
    if not _can_access_video(user, video):
        # Same error as not-found so we never confirm another user's private resource exists.
        raise ResultNotFoundError()

    if video.status != MediaStatus.READY:
        raise VideoNotReadyError()

    settings = get_settings()
    existing = result.clip
    reused = False
    wrote_new_file = False
    abs_path: pathlib.Path | None = None
    clip: GeneratedClip

    if existing is not None:
        abs_path = _clip_abs_path(existing.clip_path)
        if abs_path.exists():
            reused = True
            clip = existing
        else:
            # Cache repair: reuse the row's stored boundaries rather than re-resolving them, so a reused clip's window never changes.
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            is_audio_only = not video.mime_type.startswith("video/")
            try:
                _write_clip_file(video, existing.start_time, existing.end_time, abs_path, is_audio_only)
            except ClipGenerationError as exc:
                error_log_service.log_error(db, error_source="clip_generation", error_message=str(exc), user_id=user.id, search_result_id=result.id, video_id=video.id)
                raise
            wrote_new_file = True
            clip = existing
    else:
        try:
            instruction = match_resolver.resolve_clip_boundaries(db, result)
        except (match_resolver.InvalidTimestampsError, match_resolver.MissingDurationError) as exc:
            error_log_service.log_error(db, error_source="match_resolver", error_message=str(exc), user_id=user.id, search_result_id=result.id, video_id=video.id)
            raise

        extension = "mp3" if instruction.is_audio_only else "mp4"
        clips_dir = pathlib.Path(settings.storage_root) / "clips" / str(video.id)
        clips_dir.mkdir(parents=True, exist_ok=True)
        disk_filename = f"{uuid.uuid4().hex}.{extension}"
        abs_path = clips_dir / disk_filename
        # as_posix() keeps the stored path forward-slash even on Windows.
        relative_path = (pathlib.Path("clips") / str(video.id) / disk_filename).as_posix()

        try:
            _write_clip_file(video, instruction.start_time, instruction.end_time, abs_path, instruction.is_audio_only)
        except ClipGenerationError as exc:
            error_log_service.log_error(db, error_source="clip_generation", error_message=str(exc), user_id=user.id, search_result_id=result.id, video_id=video.id)
            raise
        wrote_new_file = True

        clip = GeneratedClip(
            result_id=result.id,
            video_id=video.id,
            start_time=instruction.start_time,
            end_time=instruction.end_time,
            clip_path=relative_path,
            # Placeholder until flush() assigns the row's id; never exposed in this intermediate state.
            clip_url="",
        )
        db.add(clip)
        try:
            db.flush()
        except IntegrityError:
            # Concurrent-create race: both requests saw result.clip as None and tried to insert a
            # GeneratedClip row; the loser's flush() raises here since result_id is UNIQUE. Recover
            # like saved_result_service.save_result: roll back, discard the orphaned file, and
            # return the winner's row as a cache hit instead of a 500.
            db.rollback()
            abs_path.unlink(missing_ok=True)
            wrote_new_file = False

            winner = (
                db.query(GeneratedClip)
                .filter(GeneratedClip.result_id == result.id)
                .first()
            )
            if winner is None:
                # Not the expected race (e.g. a real constraint problem) -- don't swallow it.
                raise
            reused = True
            clip = winner
        except SQLAlchemyError:
            db.rollback()
            abs_path.unlink(missing_ok=True)
            raise
        else:
            # clip_url is the API route, not a filesystem path; only set here since the concurrent-winner branch above already has one.
            clip.clip_url = f"/api/clips/{clip.id}"

    if result.selected_at is None:
        result.selected_at = datetime.datetime.utcnow()

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if wrote_new_file and abs_path is not None:
            abs_path.unlink(missing_ok=True)
        raise

    db.refresh(clip)
    db.refresh(result)

    return ClipResult(clip=clip, video=video, result=result, reused=reused)


# GET /api/clips/{clip_id}. Re-checks access on every call; never regenerates a missing file (that's a POST-only repair).
def get_clip_for_streaming(db: Session, user: User, clip_id: int) -> tuple[GeneratedClip, pathlib.Path, str]:
    clip = (
        db.query(GeneratedClip)
        .options(joinedload(GeneratedClip.video))
        .filter(GeneratedClip.id == clip_id)
        .first()
    )
    if clip is None:
        raise ClipNotFoundError()

    video = clip.video
    if not _can_access_video(user, video):
        raise ClipNotFoundError()

    abs_path = _clip_abs_path(clip.clip_path)
    if not abs_path.exists():
        raise MissingCachedFileError()

    is_audio_only = not video.mime_type.startswith("video/")
    media_type = "audio/mpeg" if is_audio_only else "video/mp4"
    return clip, abs_path, media_type
