"""User-self-service "forgot password" flow, matching Login.jsx's "Forgot password?" link."""

from __future__ import annotations

import datetime
import hashlib
import logging
import secrets

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.utils.security import hash_password

settings = get_settings()
logger = logging.getLogger(__name__)

# 32 random bytes (256 bits); token_urlsafe encodes this to a ~43-character single-use token.
_TOKEN_BYTES = 32


class InvalidOrExpiredTokenError(Exception):
    pass


# Only the hash is persisted; the raw token never touches the database. sha256, not bcrypt: the
# token already has 256 bits of entropy, so a fast hash is fine -- bcrypt's slowness defends
# against guessing low-entropy secrets, which doesn't apply here.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# No email provider is configured; the reset link is logged instead of sent, so the flow is
# testable locally. Swap this function's body for a real provider in production.
def _send_reset_email(email: str, raw_token: str) -> None:
    reset_link = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
    logger.info(
        "Password reset requested for %s -- reset link (development-mode delivery, not emailed): %s",
        email, reset_link,
    )


# Always returns None regardless of whether `email` matches a real account, so account
# existence is never observable -- same posture as auth_service.authenticate_user.
def request_password_reset(db: Session, email: str) -> None:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return  # silent no-op, indistinguishable from the real-account path

    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    token_row = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.datetime.utcnow()
        + datetime.timedelta(minutes=settings.password_reset_token_expire_minutes),
    )
    db.add(token_row)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    _send_reset_email(user.email, raw_token)


# Single-use and time-boxed; a used or expired token is treated identically to one that never existed.
def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    token_hash = _hash_token(raw_token)
    token_row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()

    now = datetime.datetime.utcnow()
    if token_row is None or token_row.used_at is not None or token_row.expires_at < now:
        raise InvalidOrExpiredTokenError()

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if user is None:
        # Defensive only; the FK guarantees this, but never trust that alone for a security-sensitive path.
        raise InvalidOrExpiredTokenError()

    user.password_hash = hash_password(new_password)
    token_row.used_at = now
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
