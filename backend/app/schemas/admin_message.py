from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_LENGTH = 2000


class AdminRecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    email: str


class AdminMessageOut(BaseModel):
    id: int
    sender_id: int
    sender_full_name: str
    sender_username: str
    sender_email: str
    message: str
    created_at: datetime.datetime


class SendAdminMessageRequest(BaseModel):
    recipient_admin_id: int
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message cannot be empty.")
        return stripped
