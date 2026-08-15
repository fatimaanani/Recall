from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.clip import GeneratedClipOut
from app.services import clip_service, match_resolver

router = APIRouter(tags=["clips"])


def _to_out(clip_result: clip_service.ClipResult) -> GeneratedClipOut:
    clip, video, result = clip_result.clip, clip_result.video, clip_result.result
    return GeneratedClipOut(
        generated_clip_id=clip.id,
        search_result_id=result.id,
        video_id=video.id,
        video_title=video.title,
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration=clip.end_time - clip.start_time,
        matched_text=result.matched_text,
        confidence_score=result.confidence_score,
        search_method=result.query.query_type,
        is_audio_only=not video.mime_type.startswith("video/"),
        reused=clip_result.reused,
        clip_stream_url=clip.clip_url,
    )


@router.post("/api/results/{result_id}/clip", response_model=GeneratedClipOut, status_code=status.HTTP_200_OK)
def create_or_reuse_clip(
    result_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GeneratedClipOut:
    try:
        clip_result = clip_service.get_or_create_clip(db, current_user, result_id)
    except clip_service.ResultNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found.")
    except clip_service.VideoNotReadyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This video isn't ready yet.",
        )
    except match_resolver.InvalidTimestampsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except match_resolver.MissingDurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except clip_service.SourceFileMissingError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The source media file for this video is missing.",
        )
    except clip_service.ClipGenerationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Clip generation failed. Please try again.",
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the generated clip. Please try again.",
        )
    return _to_out(clip_result)


# Re-checks access on every call rather than trusting that an earlier POST
# means this GET is safe.
@router.get("/api/clips/{clip_id}")
def stream_clip(
    clip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    try:
        clip, abs_path, media_type = clip_service.get_clip_for_streaming(db, current_user, clip_id)
    except clip_service.ClipNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found.")
    except clip_service.MissingCachedFileError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="This clip is temporarily unavailable. Try requesting it again.",
        )
    return FileResponse(abs_path, media_type=media_type)
