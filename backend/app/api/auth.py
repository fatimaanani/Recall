from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserOut
from app.services import auth_service, password_reset_service
from app.utils.rate_limit import rate_limit_by_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

# IP-keyed since none of these routes have an authenticated user yet; guards
# against brute-force, mass-registration, and reset-token abuse.
_login_rate_limit = rate_limit_by_ip(
    "auth_login", settings.rate_limit_login_max, settings.rate_limit_login_window_seconds
)
_register_rate_limit = rate_limit_by_ip(
    "auth_register", settings.rate_limit_register_max, settings.rate_limit_register_window_seconds
)
# Separate buckets so a burst against one endpoint can't exhaust the other's budget.
_forgot_password_rate_limit = rate_limit_by_ip(
    "auth_forgot_password",
    settings.rate_limit_password_reset_max,
    settings.rate_limit_password_reset_window_seconds,
)
_reset_password_rate_limit = rate_limit_by_ip(
    "auth_reset_password",
    settings.rate_limit_password_reset_max,
    settings.rate_limit_password_reset_window_seconds,
)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_register_rate_limit),
) -> TokenResponse:
    try:
        user = auth_service.register_user(db, payload)
    except auth_service.EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    except auth_service.UsernameAlreadyTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )

    token = auth_service.issue_token_for(user)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_login_rate_limit),
) -> TokenResponse:
    try:
        user = auth_service.authenticate_user(db, payload)
    except auth_service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    except auth_service.AccountSuspendedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended.",
        )

    token = auth_service.issue_token_for(user)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


# Always returns 200 with the same message regardless of whether the email
# exists, to avoid account enumeration.
@router.post("/forgot-password", status_code=status.HTTP_200_OK)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_forgot_password_rate_limit),
) -> dict:
    password_reset_service.request_password_reset(db, payload.email)
    return {"detail": "If an account exists for this email, a password reset link has been sent."}


# Generic 400 for any invalid/expired/used token, to avoid revealing which case it is.
@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(_reset_password_rate_limit),
) -> dict:
    try:
        password_reset_service.reset_password(db, payload.token, payload.new_password)
    except password_reset_service.InvalidOrExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Please request a new one.",
        )
    return {"detail": "Your password has been reset. You can now log in."}
