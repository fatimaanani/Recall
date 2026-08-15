from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    StorageUsageResponse,
    UpdateProfileRequest,
    UserOut,
)
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/storage", response_model=StorageUsageResponse)
def read_storage_usage(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> StorageUsageResponse:
    return user_service.get_storage_usage(db, current_user)


@router.patch("/me/profile", response_model=UserOut)
def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    try:
        user = user_service.update_profile(db, current_user, payload)
    except user_service.UsernameAlreadyTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )
    return user


@router.patch("/me/password", status_code=status.HTTP_200_OK)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        user_service.change_password(db, current_user, payload)
    except user_service.IncorrectPasswordError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )
    return {"message": "Password changed successfully."}


@router.delete("/me", status_code=status.HTTP_200_OK)
def delete_account(
    payload: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        user_service.delete_account(db, current_user, payload)
    except user_service.AdminSelfDeleteError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator accounts cannot be deleted through this endpoint.",
        )
    except user_service.IncorrectPasswordError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect.",
        )
    return {"message": "Account deleted successfully."}
