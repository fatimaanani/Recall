from __future__ import annotations

import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import MIN_PASSWORD_LENGTH, UserOut, validate_date_of_birth


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=255)

    # Required -- date_of_birth is the only source of truth for the minimum-age check, so making it optional would let that check be skipped.
    date_of_birth: datetime.date = Field(...)
    gender: str | None = Field(default=None, max_length=30)
    occupation: str | None = Field(default=None, max_length=100)

    @field_validator("date_of_birth")
    @classmethod
    def _check_date_of_birth(cls, value: datetime.date) -> datetime.date:
        return validate_date_of_birth(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# Always accepted at the schema level -- whether `email` matches an account is never revealed (see password_reset_service's no-enumeration contract).
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# Same MIN_PASSWORD_LENGTH rule as registration.
class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=255)
