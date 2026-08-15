from __future__ import annotations

import datetime

from pydantic import BaseModel

from app.enums import SearchBackend, SearchType


# date_from/date_to are passed as query params, not a body -- FastAPI maps these directly.
class DateRange(BaseModel):
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None


class KpiValue(BaseModel):
    value: float | int
    # None when there's no comparable previous period; the frontend shows "no comparison available" rather than a fake 0%.
    delta_percent: float | None = None
    previous_value: float | int | None = None


class ResponseTimeSeriesPoint(BaseModel):
    date: datetime.date
    exact_text_ms: float | None = None
    semantic_ms: float | None = None
    speech_to_text_ms: float | None = None


class QueryDistributionEntry(BaseModel):
    search_type: SearchType
    count: int
    percent: float


class PipelineHealth(BaseModel):
    media_processed: int
    transcript_segments_generated: int
    clips_created: int
    failed_uploads: int


class OperationalAnalyticsOut(BaseModel):
    date_from: datetime.date
    date_to: datetime.date

    search_accuracy: KpiValue | None  # None only if no evaluation exists at all (see EvaluationAnalyticsOut for the real source)
    average_response_time_ms: KpiValue
    media_files_indexed: KpiValue
    queries_processed: KpiValue

    response_time_series: list[ResponseTimeSeriesPoint]
    query_distribution: list[QueryDistributionEntry]
    total_queries: int

    pipeline_health: PipelineHealth

    # Deterministic, template-based (not fabricated) -- see
    # analytics_service.build_usage_insight
    usage_insight: str | None


class MethodEvaluationRow(BaseModel):
    search_type: SearchType
    # None (not 0.0) when this method/backend combination has no evaluated results yet; the frontend renders a dash, never a fabricated number.
    accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    sample_count: int


class EvaluationSummaryOut(BaseModel):
    best_performing_method: SearchType | None
    best_performing_note: str | None
    highest_accuracy_method: SearchType | None
    highest_accuracy_note: str | None
    fastest_method: SearchType | None
    fastest_note: str | None


class EvaluationAnalyticsOut(BaseModel):
    search_backend: SearchBackend
    date_from: datetime.date
    date_to: datetime.date

    # False if search_backend == ELASTICSEARCH and it isn't configured/
    # reachable -- distinct from "configured but zero results".
    backend_available: bool
    unavailable_reason: str | None

    overall_accuracy: float | None
    method_rows: list[MethodEvaluationRow]
    summary: EvaluationSummaryOut | None
    evaluated_test_case_count: int
    last_run_at: datetime.datetime | None
