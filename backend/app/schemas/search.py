from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.enums import SearchScope, SearchType


# query_type selects exactly one retrieval method (exact_text -> Postgres FTS, semantic -> pgvector); speech_to_text is rejected here with a service-layer error since spoken queries go through /api/search/speech instead.
class SearchRequest(BaseModel):
    query_text: str = Field(min_length=1, max_length=1000)
    query_type: SearchType
    search_scope: SearchScope = SearchScope.BOTH
    # Defaults from Settings (SEARCH_TOP_K_DEFAULT in .env), but always bounded 1-100.
    limit: int = Field(default_factory=lambda: get_settings().search_top_k_default, ge=1, le=100)


# Same shape as VideoCategoryBrief in schemas/video.py, duplicated here to avoid a cross-module dependency for a two-field shape.
class SearchResultCategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


# media_type/categories/video_uploaded_at/video_file_size_bytes are derived from the already-loaded Video row so the Results page can filter/sort without re-fetching each video; video_uploaded_at is nullable only because an in-memory Video() in a unit test hasn't gone through a real INSERT yet.
class SearchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    rank_position: int
    video_id: int
    video_title: str
    transcript_segment_id: int | None
    matched_start_time: float | None
    matched_end_time: float | None
    matched_text: str | None
    confidence_score: float
    keyword_score: float | None
    semantic_score: float | None
    has_thumbnail: bool
    # "my_library" | "shared_library", derived per-result from the video's ownership relative to the caller -- not the request's search_scope (BOTH can return a mix of both).
    library: str
    media_type: str
    categories: list[SearchResultCategoryBrief] = []
    video_uploaded_at: datetime.datetime | None = None
    video_file_size_bytes: int


# transcribed_text is only populated for a Speech-to-Text response (POST /api/search/speech); always null for typed-text search.
class SearchResponse(BaseModel):
    search_query_id: int
    query_text: str
    query_type: SearchType
    search_scope: SearchScope
    response_time_ms: float
    result_count: int
    results: list[SearchResultOut]
    transcribed_text: str | None = None


# One row per past SearchQuery, newest first, scoped to the caller only, without a results list. query_text is null for a Speech-to-Text query; transcribed_text/original_audio_filename are populated only then.
class SearchHistoryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query_text: str | None
    transcribed_text: str | None
    original_audio_filename: str | None
    query_type: SearchType
    search_scope: SearchScope
    results_found: int
    response_time_ms: float | None
    created_at: datetime.datetime
