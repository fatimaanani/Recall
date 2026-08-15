from __future__ import annotations

from pydantic import BaseModel

from app.enums import SearchType


# clip_stream_url is always the authenticated GET /api/clips/{id} route, never a raw path -- JWT auth means the frontend must fetch it as a blob (see useProtectedMedia.js) rather than use it directly in a <video src=...>.
class GeneratedClipOut(BaseModel):
    generated_clip_id: int
    search_result_id: int
    video_id: int
    video_title: str
    start_time: float
    end_time: float
    duration: float
    matched_text: str | None
    confidence_score: float
    search_method: SearchType
    is_audio_only: bool
    reused: bool
    clip_stream_url: str
