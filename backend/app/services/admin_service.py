from __future__ import annotations

import logging
import pathlib

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.enums import AccountStatus, UserRole
from app.models.admin_message import AdminMessage
from app.models.user import User
from app.models.video import Video
from app.models.video_category import VideoCategory
from app.schemas.admin_message import AdminMessageOut, AdminRecipientOut
from app.schemas.user import AdminUserOut
from app.schemas.video import AdminVideoOut
from app.services import admin_audit_log_service, video_service

logger = logging.getLogger(__name__)


class UserNotFoundError(Exception):
    pass


class UsernameMismatchError(Exception):
    pass


class AlreadyAdminError(Exception):
    pass


class UploadNotFoundError(Exception):
    pass


class RecipientNotFoundError(Exception):
    pass


class RecipientInactiveError(Exception):
    pass


class SelfMessageError(Exception):
    pass


def _row_to_admin_user_out(user: User, upload_count: int, used_bytes: int | None) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        account_status=user.account_status,
        created_at=user.created_at,
        storage_used_bytes=int(used_bytes or 0),
        upload_count=int(upload_count or 0),
        gender=user.gender,
        occupation=user.occupation,
        date_of_birth=user.date_of_birth,
    )


def list_users(db: Session) -> list[AdminUserOut]:
    rows = (
        db.query(
            User,
            func.count(Video.id),
            func.coalesce(func.sum(Video.file_size_bytes), 0),
        )
        .outerjoin(Video, Video.owner_id == User.id)
        .filter(User.role == UserRole.USER)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .all()
    )
    return [_row_to_admin_user_out(user, count, used) for user, count, used in rows]


def _get_target_user_or_none(db: Session, user_id: int) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role != UserRole.USER:
        return None
    return user


def set_account_status(db: Session, actor: User, user_id: int, new_status: AccountStatus) -> AdminUserOut:
    user = _get_target_user_or_none(db, user_id)
    if user is None:
        raise UserNotFoundError()

    user.account_status = new_status
    action = (
        admin_audit_log_service.ACTION_SUSPEND
        if new_status == AccountStatus.SUSPENDED
        else admin_audit_log_service.ACTION_REACTIVATE
    )
    admin_audit_log_service.record(db, actor=actor, target=user, action=action)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(user)

    upload_count = db.query(func.count(Video.id)).filter(Video.owner_id == user.id).scalar()
    used_bytes = (
        db.query(func.coalesce(func.sum(Video.file_size_bytes), 0))
        .filter(Video.owner_id == user.id)
        .scalar()
    )
    return _row_to_admin_user_out(user, upload_count, used_bytes)


def suspend_user(db: Session, actor: User, user_id: int) -> AdminUserOut:
    return set_account_status(db, actor, user_id, AccountStatus.SUSPENDED)


def reactivate_user(db: Session, actor: User, user_id: int) -> AdminUserOut:
    return set_account_status(db, actor, user_id, AccountStatus.ACTIVE)


# Audit row is staged before the delete; its target_user_id FK is SET NULL rather than CASCADE, so the record survives the user's deletion.
def delete_user_by_admin(db: Session, actor: User, user_id: int, confirm_username: str) -> None:
    user = _get_target_user_or_none(db, user_id)
    if user is None:
        raise UserNotFoundError()

    if confirm_username != user.username:
        raise UsernameMismatchError()

    admin_audit_log_service.record(db, actor=actor, target=user, action=admin_audit_log_service.ACTION_DELETE)
    db.delete(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _find_any_user_by_email(db: Session, email: str) -> User:
    normalized_email = email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user is None:
        raise UserNotFoundError()
    return user


def find_user_by_email(db: Session, email: str) -> User:
    return _find_any_user_by_email(db, email)


def promote_user_to_admin(db: Session, actor: User, email: str) -> User:
    user = _find_any_user_by_email(db, email)

    if user.role == UserRole.ADMIN:
        raise AlreadyAdminError()

    user.role = UserRole.ADMIN
    admin_audit_log_service.record(db, actor=actor, target=user, action=admin_audit_log_service.ACTION_PROMOTE)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(user)

    logger.info(
        "Admin promotion: user id=%s email=%s promoted to admin",
        user.id,
        user.email,
    )
    return user


def _derive_file_type(original_filename: str) -> str:
    suffix = pathlib.Path(original_filename).suffix.lstrip(".").upper()
    return suffix or "UNKNOWN"


def _row_to_admin_video_out(video: Video, username: str) -> AdminVideoOut:
    return AdminVideoOut(
        id=video.id,
        username=username,
        file_name=video.original_filename,
        file_type=_derive_file_type(video.original_filename),
        uploaded_at=video.uploaded_at,
    )


def list_user_uploads(db: Session) -> list[AdminVideoOut]:
    rows = (
        db.query(Video, User.username)
        .join(User, Video.owner_id == User.id)
        .filter(User.role == UserRole.USER)
        .order_by(Video.uploaded_at.desc())
        .all()
    )
    return [_row_to_admin_video_out(video, username) for video, username in rows]


def get_user_uploads(db: Session, user_id: int) -> list[Video]:
    user = _get_target_user_or_none(db, user_id)
    if user is None:
        raise UserNotFoundError()

    return (
        db.query(Video)
        .options(selectinload(Video.category_links).selectinload(VideoCategory.category))
        .filter(Video.owner_id == user_id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )


def get_user_upload_detail(db: Session, video_id: int) -> Video:
    video = (
        db.query(Video)
        .options(selectinload(Video.category_links).selectinload(VideoCategory.category))
        .join(User, Video.owner_id == User.id)
        .filter(Video.id == video_id, User.role == UserRole.USER)
        .first()
    )
    if video is None:
        raise UploadNotFoundError()
    return video


def delete_user_upload(db: Session, video_id: int) -> None:
    video = (
        db.query(Video)
        .join(User, Video.owner_id == User.id)
        .filter(Video.id == video_id, User.role == UserRole.USER)
        .first()
    )
    if video is None:
        raise UploadNotFoundError()

    video_service.purge_video(db, video)


def list_active_administrators(db: Session, current_admin: User) -> list[AdminRecipientOut]:
    admins = (
        db.query(User)
        .filter(
            User.role == UserRole.ADMIN,
            User.account_status == AccountStatus.ACTIVE,
            User.id != current_admin.id,
        )
        .order_by(User.full_name)
        .all()
    )
    return [AdminRecipientOut.model_validate(admin) for admin in admins]


def list_received_messages(db: Session, current_admin: User) -> list[AdminMessageOut]:
    rows = (
        db.query(AdminMessage, User)
        .join(User, AdminMessage.sender_admin_id == User.id)
        .filter(AdminMessage.recipient_admin_id == current_admin.id)
        .order_by(AdminMessage.created_at.desc())
        .all()
    )
    return [
        AdminMessageOut(
            id=admin_message.id,
            sender_id=sender.id,
            sender_full_name=sender.full_name,
            sender_username=sender.username,
            sender_email=sender.email,
            message=admin_message.message,
            created_at=admin_message.created_at,
        )
        for admin_message, sender in rows
    ]


def send_admin_message(db: Session, sender: User, recipient_admin_id: int, message: str) -> AdminMessage:
    if recipient_admin_id == sender.id:
        raise SelfMessageError()

    recipient = db.query(User).filter(User.id == recipient_admin_id).first()
    if recipient is None or recipient.role != UserRole.ADMIN:
        raise RecipientNotFoundError()
    if recipient.account_status == AccountStatus.SUSPENDED:
        raise RecipientInactiveError()

    admin_message = AdminMessage(
        sender_admin_id=sender.id,
        recipient_admin_id=recipient.id,
        message=message,
    )
    db.add(admin_message)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(admin_message)
    return admin_message
