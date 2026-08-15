from __future__ import annotations

import datetime

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.enums import AccountStatus, UserRole
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.utils.security import create_access_token, hash_password, verify_password


class EmailAlreadyRegisteredError(Exception):
    pass


class UsernameAlreadyTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountSuspendedError(Exception):
    pass


def register_user(db: Session, payload: RegisterRequest) -> User:
    existing_email = db.query(User).filter(User.email == payload.email).first()
    if existing_email is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    existing_username = db.query(User).filter(User.username == payload.username).first()
    if existing_username is not None:
        raise UsernameAlreadyTakenError(payload.username)

    user = User(
        full_name=payload.full_name,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        occupation=payload.occupation,
        role=UserRole.USER,
        account_status=AccountStatus.ACTIVE,
    )
    db.add(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(user)
    return user


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    user = (
        db.query(User)
        .filter(or_(User.email == payload.email, User.username == payload.email))
        .first()
    )
    # Generic error either way, no email enumeration
    if user is None or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentialsError()

    if user.account_status == AccountStatus.SUSPENDED:
        raise AccountSuspendedError()

    user.last_login = datetime.datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def issue_token_for(user: User) -> str:
    return create_access_token(subject=str(user.id), role=user.role.value)
