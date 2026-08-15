from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict

from app.enums import SearchType


# Deliberately tiny -- just enough for the frontend to flip the bookmark icon, not a full result re-statement.
class SavedResultOut(BaseModel):
    saved_result_id: int
    result_id: int
    saved_at: datetime.datetime
    is_saved: bool = True


# Deliberately flat -- every field the Upload Details row needs without a second per-row request; clip_stream_url is the only way to reach the bytes, same convention as GeneratedClipOut.
class SavedSceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    saved_result_id: int
    result_id: int
    generated_clip_id: int
    video_id: int
    video_title: str
    start_time: float
    end_time: float
    duration: float
    confidence_score: float
    search_method: SearchType
    matched_text: str | None
    saved_at: datetime.datetime
    has_thumbnail: bool
    media_type: str
    clip_stream_url: str
