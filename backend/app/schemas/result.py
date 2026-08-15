from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.enums import SearchScope, SearchType


class ResultDetailCategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ResultClipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_clip_id: int
    start_time: float
    end_time: float
    duration: float
    clip_stream_url: str
    is_audio_only: bool


# Exists so Scene Viewer can render its full match panel from resultId alone (on refresh, direct nav, or a saved scene) rather than relying on React Router state.
class ResultDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    video_id: int
    video_title: str
    media_type: str
    transcript_segment_id: int | None
    matched_start_time: float | None
    matched_end_time: float | None
    matched_text: str | None
    confidence_score: float
    keyword_score: float | None
    semantic_score: float | None
    rank_position: int
    query_text: str | None
    query_type: SearchType
    search_scope: SearchScope
    categories: list[ResultDetailCategoryBrief] = []
    # None if no clip has been generated for this result yet.
    clip: ResultClipSummary | None = None
    # Current caller's own bookmark state -- never another user's.
    is_saved: bool = False

    # Deterministic and transcript-grounded, never fabricated; all three are None/empty when there's no clip yet or no overlapping transcript segments.
    transcript_span_text: str | None = None
    summary: str | None = None
    key_points: list[str] = []
