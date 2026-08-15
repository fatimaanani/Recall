from __future__ import annotations

import datetime

from pydantic import BaseModel, Field

from app.schemas.video import VideoOut


class CategoryOut(BaseModel):
    id: int
    name: str
    video_count: int
    created_at: datetime.datetime


class CategoryDetailOut(CategoryOut):
    videos: list[VideoOut] = []


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


# Same shape as CategoryCreateRequest, kept separate so the two can diverge later.
class CategoryRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
