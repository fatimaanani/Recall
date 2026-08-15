from __future__ import annotations

import pathlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_admin
from app.models.user import User
from app.schemas.admin_message import AdminMessageOut, AdminRecipientOut, SendAdminMessageRequest
from app.schemas.user import (
    AdminDeleteUserRequest,
    AdminUserLookupOut,
    AdminUserLookupRequest,
    AdminUserOut,
    PromoteToAdminRequest,
)
from app.schemas.video import AdminVideoOut, VideoOut, video_to_out
from app.services import admin_service
from app.services.media_processing_service import backfill_missing_embeddings_task

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[AdminUserOut]:
    return admin_service.list_users(db)


@router.patch("/users/{user_id}/suspend", response_model=AdminUserOut)
def suspend_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    try:
        return admin_service.suspend_user(db, current_admin, user_id)
    except admin_service.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


@router.patch("/users/{user_id}/reactivate", response_model=AdminUserOut)
def reactivate_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    try:
        return admin_service.reactivate_user(db, current_admin, user_id)
    except admin_service.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: int,
    payload: AdminDeleteUserRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        admin_service.delete_user_by_admin(db, current_admin, user_id, payload.username)
    except admin_service.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    except admin_service.UsernameMismatchError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The username you entered doesn't match this account.",
        )
    return {"message": "Account deleted successfully."}


@router.post("/users/lookup-by-email", response_model=AdminUserLookupOut)
def lookup_user_by_email(
    payload: AdminUserLookupRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> User:
    try:
        user = admin_service.find_user_by_email(db, payload.email)
    except admin_service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with that email.",
        )
    return user


@router.post("/promote-to-admin", status_code=status.HTTP_200_OK)
def promote_to_admin(
    payload: PromoteToAdminRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        user = admin_service.promote_user_to_admin(db, current_admin, payload.email)
    except admin_service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with that email.",
        )
    except admin_service.AlreadyAdminError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account is already an administrator.",
        )
    return {"message": f"{user.email} has been promoted to administrator."}


@router.get("/users/{user_id}/uploads", response_model=list[VideoOut])
def list_user_uploads_detail(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[VideoOut]:
    try:
        videos = admin_service.get_user_uploads(db, user_id)
    except admin_service.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return [video_to_out(v) for v in videos]


@router.get("/uploads", response_model=list[AdminVideoOut])
def list_uploads(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[AdminVideoOut]:
    return admin_service.list_user_uploads(db)


@router.get("/uploads/{video_id}", response_model=VideoOut)
def read_upload_detail(
    video_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> VideoOut:
    try:
        video = admin_service.get_user_upload_detail(db, video_id)
    except admin_service.UploadNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")
    return video_to_out(video)


@router.get("/uploads/{video_id}/thumbnail")
def read_upload_thumbnail(
    video_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FileResponse:
    try:
        video = admin_service.get_user_upload_detail(db, video_id)
    except admin_service.UploadNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")

    if not video.thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No thumbnail available.")

    thumbnail_path = pathlib.Path(settings.storage_root) / video.thumbnail_path
    if not thumbnail_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No thumbnail available.")

    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.delete("/uploads/{video_id}", status_code=status.HTTP_200_OK)
def delete_upload(
    video_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        admin_service.delete_user_upload(db, video_id)
    except admin_service.UploadNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found.")
    return {"message": "Upload deleted successfully."}


@router.get("/messages/administrators", response_model=list[AdminRecipientOut])
def list_message_administrators(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[AdminRecipientOut]:
    return admin_service.list_active_administrators(db, current_admin)


@router.get("/messages/received", response_model=list[AdminMessageOut])
def list_received_messages(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[AdminMessageOut]:
    return admin_service.list_received_messages(db, current_admin)


@router.post("/messages", status_code=status.HTTP_200_OK)
def send_admin_message(
    payload: SendAdminMessageRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        admin_service.send_admin_message(db, current_admin, payload.recipient_admin_id, payload.message)
    except admin_service.SelfMessageError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot send a message to yourself.",
        )
    except admin_service.RecipientNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient administrator not found.",
        )
    except admin_service.RecipientInactiveError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This administrator's account is currently suspended.",
        )
    return {"message": "Message sent."}


@router.post("/backfill-embeddings", status_code=status.HTTP_202_ACCEPTED)
def backfill_embeddings(
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin),
) -> dict[str, str]:
    # Returns immediately; the actual work runs in backfill_missing_embeddings_task,
    # which opens its own DB session. A lock in that function makes overlapping
    # backfills a harmless no-op.
    background_tasks.add_task(backfill_missing_embeddings_task)
    return {"message": "Embedding backfill started."}
