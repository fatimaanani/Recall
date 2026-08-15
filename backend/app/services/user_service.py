from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.enums import UserRole
from app.models.user import User
from app.models.video import Video
from app.schemas.user import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    StorageUsageResponse,
    UpdateProfileRequest,
)
from app.utils.security import hash_password, verify_password


class IncorrectPasswordError(Exception):
    pass


class AdminSelfDeleteError(Exception):
    pass


class UsernameAlreadyTakenError(Exception):
    pass


def get_storage_usage(db: Session, user: User) -> StorageUsageResponse:
    used_bytes = (
        db.query(func.coalesce(func.sum(Video.file_size_bytes), 0))
        .filter(Video.owner_id == user.id)
        .scalar()
    )
    return StorageUsageResponse(used_bytes=int(used_bytes), limit_bytes=user.storage_limit_bytes)


def change_password(db: Session, user: User, payload: ChangePasswordRequest) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise IncorrectPasswordError()

    user.password_hash = hash_password(payload.new_password)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def update_profile(db: Session, user: User, payload: UpdateProfileRequest) -> User:
    update_data = payload.model_dump(exclude_unset=True)

    if "username" in update_data:
        new_username = update_data.pop("username")
        # Skip uniqueness check if unchanged
        if new_username is not None and new_username != user.username:
            existing = (
                db.query(User)
                .filter(User.username == new_username, User.id != user.id)
                .first()
            )
            if existing is not None:
                raise UsernameAlreadyTakenError(new_username)
            user.username = new_username

    if "full_name" in update_data:
        new_full_name = update_data.pop("full_name")
        if new_full_name is not None:
            user.full_name = new_full_name

    # Remaining nullable fields
    for field, value in update_data.items():
        setattr(user, field, value)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(user)
    return user


def delete_account(db: Session, user: User, payload: DeleteAccountRequest) -> None:
    if user.role == UserRole.ADMIN:
        raise AdminSelfDeleteError()

    if not verify_password(payload.password, user.password_hash):
        raise IncorrectPasswordError()

    db.delete(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
