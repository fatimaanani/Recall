from __future__ import annotations

import pathlib

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.saved_result import SavedSceneOut
from app.schemas.video import TranscriptSegmentOut, VideoOut, VideoRenameRequest, video_to_out
from app.services import media_processing_service, saved_result_service, video_service
from app.utils.file_validation import UnsupportedFileTypeError
from app.utils.rate_limit import rate_limit_by_user
from app.utils.subtitle_validation import InvalidSubtitleFileError

router = APIRouter(prefix="/api/videos", tags=["videos"])
settings = get_settings()
# User-keyed: guards against one account hammering storage/FFmpeg/Whisper,
# not anonymous abuse.
_upload_rate_limit = rate_limit_by_user(
    "video_upload", settings.rate_limit_upload_max, settings.rate_limit_upload_window_seconds
)


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    # Optional subtitle file; takes precedence over embedded/Whisper-generated subtitles.
    subtitle_file: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_upload_rate_limit),
) -> VideoOut:
    try:
        video = await video_service.save_upload(db, current_user, file, title, subtitle_file)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    except InvalidSubtitleFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except video_service.FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        )
    except video_service.StorageQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        )
    except video_service.DuplicateFileError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This file has already been uploaded.",
        )
    background_tasks.add_task(media_processing_service.process_video, video.id)
    return video_to_out(video)


@router.get("", response_model=list[VideoOut])
def list_videos(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[VideoOut]:
    videos = video_service.list_videos(db, current_user)
    return [video_to_out(v) for v in videos]


@router.get("/{video_id}", response_model=VideoOut)
def read_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoOut:
    try:
        video = video_service.get_video(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        # 404 not 403: a private video owned by someone else should look
        # identical to a nonexistent id.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    out = video_to_out(video)
    out.current_stage = video_service.get_current_processing_stage(db, video.id)
    return out


@router.get("/{video_id}/thumbnail")
def read_video_thumbnail(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    try:
        video = video_service.get_video(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")

    if not video.thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No thumbnail available.")

    thumbnail_path = pathlib.Path(settings.storage_root) / video.thumbnail_path
    if not thumbnail_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No thumbnail available.")

    return FileResponse(thumbnail_path, media_type="image/jpeg")


# Re-checks access on every call, and never exposes the real filesystem path
# to the frontend.
@router.get("/{video_id}/stream")
def stream_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    try:
        _video, abs_path, media_type = video_service.get_video_stream_path(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    except video_service.SourceFileMissingError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The original file for this upload is missing.",
        )
    return FileResponse(abs_path, media_type=media_type)


@router.get("/{video_id}/transcript", response_model=list[TranscriptSegmentOut])
def read_video_transcript(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TranscriptSegmentOut]:
    try:
        segments = video_service.get_transcript_segments(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    return [TranscriptSegmentOut.model_validate(s) for s in segments]


# Only the current user's own saved bookmarks; never exposes another user's
# saved state.
def _saved_scene_to_out(scene: saved_result_service.SavedScene) -> SavedSceneOut:
    video, clip, result = scene.video, scene.clip, scene.result
    return SavedSceneOut(
        saved_result_id=scene.saved_result.id,
        result_id=result.id,
        generated_clip_id=clip.id,
        video_id=video.id,
        video_title=video.title,
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration=clip.end_time - clip.start_time,
        confidence_score=result.confidence_score,
        search_method=result.query.query_type,
        matched_text=result.matched_text,
        saved_at=scene.saved_result.created_at,
        has_thumbnail=video.thumbnail_path is not None,
        media_type="video" if video.mime_type.startswith("video/") else "audio",
        clip_stream_url=clip.clip_url,
    )


@router.get("/{video_id}/saved-results", response_model=list[SavedSceneOut])
def read_saved_results_for_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedSceneOut]:
    try:
        scenes = saved_result_service.list_saved_for_video(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    return [_saved_scene_to_out(s) for s in scenes]


@router.patch("/{video_id}", response_model=VideoOut)
def rename_video(
    video_id: int,
    payload: VideoRenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoOut:
    try:
        video = video_service.rename_video(db, current_user, video_id, payload.title)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    return video_to_out(video)


@router.post("/{video_id}/reprocess", response_model=VideoOut)
def reprocess_video(
    video_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoOut:
    try:
        video = video_service.reprocess_video(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    except video_service.InvalidReprocessStateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a failed video can be reprocessed.",
        )
    background_tasks.add_task(media_processing_service.process_video, video.id)
    return video_to_out(video)


@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
def delete_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        video_service.delete_video(db, current_user, video_id)
    except video_service.VideoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found.")
    return {"message": "Video deleted successfully."}
