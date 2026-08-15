from __future__ import annotations

import hashlib
import logging
import pathlib
import uuid

from fastapi import UploadFile
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource, UserRole
from app.models.processing_log import ProcessingLog
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory
from app.services import elasticsearch_service, error_log_service
from app.utils.file_validation import validate_upload
from app.utils.subtitle_validation import InvalidSubtitleFileError, validate_subtitle_upload

# Kept as "whisper_transcription" even though this stage may resolve a subtitle instead of
# Whisper; the frontend Upload Queue keys off this exact value.
_UPLOAD_QUEUE_RELEVANT_STAGES = ("metadata_extraction", "whisper_transcription")

settings = get_settings()
logger = logging.getLogger(__name__)

_CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB

_SIGNATURE_HEAD_BYTES = 16


class FileTooLargeError(Exception):
    pass


class StorageQuotaExceededError(Exception):
    pass


class VideoNotFoundError(Exception):
    pass


class InvalidReprocessStateError(Exception):
    pass


class DuplicateFileError(Exception):
    pass


class SourceFileMissingError(Exception):
    """The database row exists but the original file is gone from disk -- a data-integrity
    problem, not something the caller did wrong."""


def _get_used_bytes(db: Session, owner_id: int) -> int:
    return int(
        db.query(func.coalesce(func.sum(Video.file_size_bytes), 0))
        .filter(Video.owner_id == owner_id)
        .scalar()
    )


# subtitle_file is optional; when provided, the row is created with subtitle_source=UPLOADED so
# the processing pipeline skips straight to it.
async def save_upload(
    db: Session, user: User, file: UploadFile, title: str, subtitle_file: UploadFile | None = None
) -> Video:
    head = await file.read(_SIGNATURE_HEAD_BYTES)
    await file.seek(0)

    extension, mime_type = validate_upload(file.filename or "", head)

    # Subtitle validation happens before any disk I/O for the video file, so a bad subtitle
    # fails fast with nothing to clean up.
    subtitle_bytes: bytes | None = None
    subtitle_extension: str | None = None
    if subtitle_file is not None:
        subtitle_bytes = await subtitle_file.read()
        await subtitle_file.close()
        subtitle_extension = validate_subtitle_upload(
            subtitle_file.filename or "", subtitle_bytes, settings.max_subtitle_upload_size_bytes
        )

    if user.role == UserRole.ADMIN:
        source_type = MediaSourceType.ADMIN_PRELOADED
        visibility = MediaVisibility.SHARED
    else:
        source_type = MediaSourceType.USER_UPLOAD
        visibility = MediaVisibility.PRIVATE

    used_bytes = _get_used_bytes(db, user.id)
    remaining_bytes = user.storage_limit_bytes - used_bytes

    # Server-generated filename, no path traversal
    owner_dir = pathlib.Path(settings.storage_root) / "videos" / str(user.id)
    owner_dir.mkdir(parents=True, exist_ok=True)
    disk_filename = f"{uuid.uuid4().hex}.{extension}"
    disk_path = owner_dir / disk_filename

    total_bytes = 0
    # SHA-256 checksum, computed while streaming
    hasher = hashlib.sha256()
    try:
        with open(disk_path, "wb") as out_file:
            while chunk := await file.read(_CHUNK_SIZE_BYTES):
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds the {settings.max_upload_size_bytes} byte upload limit."
                    )
                if total_bytes > remaining_bytes:
                    raise StorageQuotaExceededError(
                        "This upload would exceed your remaining storage quota."
                    )
                out_file.write(chunk)
                hasher.update(chunk)
    except (FileTooLargeError, StorageQuotaExceededError):
        disk_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    checksum = hasher.hexdigest()

    if user.role == UserRole.ADMIN:
        duplicate_scope = Video.visibility == MediaVisibility.SHARED
    else:
        duplicate_scope = Video.owner_id == user.id
    existing_duplicate = (
        db.query(Video)
        .filter(duplicate_scope, Video.file_checksum == checksum)
        .first()
    )
    if existing_duplicate is not None:
        # Remove this attempt's file, keep the original
        disk_path.unlink(missing_ok=True)
        raise DuplicateFileError()

    # Written only after every video-file check above has passed, avoiding a write-then-delete
    # on a duplicate/quota rejection.
    subtitle_disk_path: pathlib.Path | None = None
    subtitle_relative_path: str | None = None
    if subtitle_bytes is not None and subtitle_extension is not None:
        subtitle_dir = pathlib.Path(settings.storage_root) / "subtitles" / str(user.id)
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_disk_filename = f"{uuid.uuid4().hex}.{subtitle_extension}"
        subtitle_disk_path = subtitle_dir / subtitle_disk_filename
        subtitle_disk_path.write_bytes(subtitle_bytes)
        # as_posix() keeps the stored path forward-slash even on Windows.
        subtitle_relative_path = (pathlib.Path("subtitles") / str(user.id) / subtitle_disk_filename).as_posix()

    video = Video(
        owner_id=user.id,
        title=title,
        original_filename=file.filename or disk_filename,
        # as_posix() for portability, same reasoning as subtitle_relative_path above.
        file_path=(pathlib.Path("videos") / str(user.id) / disk_filename).as_posix(),
        file_size_bytes=total_bytes,
        mime_type=mime_type,
        file_checksum=checksum,
        status=MediaStatus.UPLOADED,
        source_type=source_type,
        visibility=visibility,
        subtitle_path=subtitle_relative_path,
        subtitle_source=SubtitleSource.UPLOADED if subtitle_relative_path else SubtitleSource.NONE,
        has_subtitles=subtitle_relative_path is not None,
    )
    db.add(video)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        # Avoid orphaned files on failed commit
        disk_path.unlink(missing_ok=True)
        if subtitle_disk_path is not None:
            subtitle_disk_path.unlink(missing_ok=True)
        raise
    db.refresh(video)
    return video


def list_videos(db: Session, user: User) -> list[Video]:
    return (
        db.query(Video)
        .options(selectinload(Video.category_links).selectinload(VideoCategory.category))
        .filter(or_(Video.owner_id == user.id, Video.visibility == MediaVisibility.SHARED))
        .order_by(Video.uploaded_at.desc())
        .all()
    )


def _get_owned_video_or_none(db: Session, user: User, video_id: int) -> Video | None:
    video = (
        db.query(Video)
        .options(selectinload(Video.category_links).selectinload(VideoCategory.category))
        .filter(Video.id == video_id)
        .first()
    )
    if video is None:
        return None
    if video.owner_id != user.id and video.visibility != MediaVisibility.SHARED:
        return None
    return video


def get_video(db: Session, user: User, video_id: int) -> Video:
    video = _get_owned_video_or_none(db, user, video_id)
    if video is None:
        raise VideoNotFoundError()
    return video


# Used by Upload Queue polling.
def get_current_processing_stage(db: Session, video_id: int) -> str | None:
    log = (
        db.query(ProcessingLog)
        .filter(
            ProcessingLog.video_id == video_id,
            ProcessingLog.process_type.in_(_UPLOAD_QUEUE_RELEVANT_STAGES),
        )
        .order_by(ProcessingLog.id.desc())
        .first()
    )
    return log.process_type if log else None


# Re-checks owner-or-shared authorization on every call via get_video. Whole-file only, no HTTP
# Range/206 support -- large files take longer to begin playback. Returns the stored mime_type
# as-is, unlike clip_service's streaming which normalizes to video/mp4 or audio/mpeg.
def get_video_stream_path(db: Session, user: User, video_id: int) -> tuple[Video, pathlib.Path, str]:
    video = get_video(db, user, video_id)
    abs_path = pathlib.Path(settings.storage_root) / video.file_path
    if not abs_path.exists():
        raise SourceFileMissingError()
    return video, abs_path, video.mime_type


# Authorization delegated to get_video. Transcript content can only ever be written by the
# processing pipeline, never by a user request.
def get_transcript_segments(db: Session, user: User, video_id: int) -> list[TranscriptSegment]:
    get_video(db, user, video_id)
    return (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.start_time.asc())
        .all()
    )


def rename_video(db: Session, user: User, video_id: int, new_title: str) -> Video:
    video = db.query(Video).filter(Video.id == video_id, Video.owner_id == user.id).first()
    if video is None:
        raise VideoNotFoundError()

    video.title = new_title
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(video)
    return video


def reprocess_video(db: Session, user: User, video_id: int) -> Video:
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise VideoNotFoundError()
    if user.role != UserRole.ADMIN and video.owner_id != user.id:
        raise VideoNotFoundError()

    if video.status != MediaStatus.FAILED:
        raise InvalidReprocessStateError()

    video.status = MediaStatus.PROCESSING
    video.processing_error = None
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(video)
    return video


def purge_video(db: Session, video: Video) -> None:
    disk_path = pathlib.Path(settings.storage_root) / video.file_path
    disk_path.unlink(missing_ok=True)

    if video.thumbnail_path:
        thumbnail_path = pathlib.Path(settings.storage_root) / video.thumbnail_path
        thumbnail_path.unlink(missing_ok=True)

    if video.subtitle_path:
        subtitle_path = pathlib.Path(settings.storage_root) / video.subtitle_path
        subtitle_path.unlink(missing_ok=True)

    # Captured before the delete below, since SQLAlchemy expires video.id once the commit
    # succeeds. The Elasticsearch cleanup below is evaluation-only, best-effort, and never
    # blocks a real deletion.
    video_id = video.id
    segment_ids = [row.id for row in db.query(TranscriptSegment.id).filter(TranscriptSegment.video_id == video_id).all()]

    db.delete(video)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    try:
        for segment_id in segment_ids:
            elasticsearch_service.delete_segment(segment_id)
    except elasticsearch_service.ElasticsearchUnavailableError:
        pass  # disabled/unreachable is the expected default state, nothing to log
    except Exception as exc:  # noqa: BLE001 -- evaluation-index cleanup must never fail a real deletion, which already committed above
        # video_id isn't passed to error_log_service here, since the video row no longer exists
        # after the commit above and a foreign key referencing it would fail; the id goes in the
        # message text instead.
        logger.warning("Elasticsearch cleanup failed after deleting video %s: %s", video_id, exc)
        error_log_service.log_error(db, error_source="elasticsearch_sync", error_message=f"video_id={video_id}: {exc}")


def delete_video(db: Session, user: User, video_id: int) -> None:
    video = db.query(Video).filter(Video.id == video_id, Video.owner_id == user.id).first()
    if video is None:
        raise VideoNotFoundError()

    purge_video(db, video)
