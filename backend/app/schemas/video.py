from __future__ import annotations

import datetime
import typing

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.enums import MediaSourceType, MediaStatus, MediaVisibility

if typing.TYPE_CHECKING:
    from app.models.video import Video


class VideoCategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    original_filename: str
    file_size_bytes: int
    mime_type: str
    duration_seconds: float | None
    status: MediaStatus
    source_type: MediaSourceType
    visibility: MediaVisibility
    has_subtitles: bool
    # Whether every transcript segment has an embedding yet; independent of `status` (see app/models/video.py).
    has_embeddings: bool = False
    processing_error: str | None = None
    uploaded_at: datetime.datetime
    categories: list[VideoCategoryBrief] = []
    has_thumbnail: bool = False
    # Active processing stage, read_video only
    current_stage: str | None = None

    @computed_field
    @property
    def media_type(self) -> str:
        return "video" if self.mime_type.startswith("video/") else "audio"


class VideoRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


# Read-only by design -- no PATCH/PUT exists for transcript content anywhere in this project.
class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_time: float
    end_time: float
    text: str


class AdminVideoOut(BaseModel):
    id: int
    username: str
    file_name: str
    file_type: str
    uploaded_at: datetime.datetime


def video_to_out(video: "Video") -> VideoOut:
    out = VideoOut.model_validate(video)
    out.categories = [
        VideoCategoryBrief(id=link.category.id, name=link.category.name)
        for link in video.category_links
    ]
    out.has_thumbnail = video.thumbnail_path is not None
    return out
