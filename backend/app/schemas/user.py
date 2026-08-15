from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.enums import AccountStatus, UserRole

MIN_PASSWORD_LENGTH = 8

# No formal requirement specifies a minimum age, so 13 is a deliberate default, not an assumption of an adults-only product.
MIN_REGISTRATION_AGE = 13


# Shared by registration (required) and profile updates (optional); computed by real year/month/day comparison, never a naive year subtraction which overcounts age before the birthday.
def validate_date_of_birth(value: datetime.date) -> datetime.date:
    today = datetime.date.today()
    if value > today:
        raise ValueError("Date of birth cannot be in the future.")

    age = today.year - value.year
    if (today.month, today.day) < (value.month, value.day):
        age -= 1

    if age < MIN_REGISTRATION_AGE:
        raise ValueError(f"You must be at least {MIN_REGISTRATION_AGE} years old.")

    return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str
    date_of_birth: datetime.date | None
    gender: str | None
    occupation: str | None
    role: UserRole
    account_status: AccountStatus
    email_verified: bool
    last_login: datetime.datetime | None
    created_at: datetime.datetime


class StorageUsageResponse(BaseModel):
    used_bytes: int
    limit_bytes: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=255)


class DeleteAccountRequest(BaseModel):
    password: str


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    username: str | None = Field(default=None, min_length=1, max_length=80)
    gender: str | None = Field(default=None, max_length=30)
    occupation: str | None = Field(default=None, max_length=100)
    date_of_birth: datetime.date | None = None

    # Stays optional (an update that doesn't touch it must keep working), but if sent, must pass the same age/date rule as registration.
    @field_validator("date_of_birth")
    @classmethod
    def _check_date_of_birth(cls, value: datetime.date | None) -> datetime.date | None:
        if value is None:
            return value
        return validate_date_of_birth(value)


class AdminUserOut(BaseModel):
    id: int
    full_name: str
    username: str
    email: str
    account_status: AccountStatus
    created_at: datetime.datetime
    storage_used_bytes: int
    upload_count: int
    gender: str | None
    occupation: str | None
    date_of_birth: datetime.date | None


class AdminUserLookupRequest(BaseModel):
    email: EmailStr


class AdminUserLookupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str
    role: UserRole
    account_status: AccountStatus


class PromoteToAdminRequest(BaseModel):
    email: EmailStr


class AdminDeleteUserRequest(BaseModel):
    username: str
