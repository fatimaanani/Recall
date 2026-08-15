"""Operational analytics are built from real live-application data only and are kept structurally separate from the evaluation backend used by evaluation_service.py."""

from __future__ import annotations

import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums import MediaStatus, SearchType
from app.models.generated_clip import GeneratedClip
from app.models.search_query import SearchQuery
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video
from app.schemas.analytics import (
    KpiValue,
    OperationalAnalyticsOut,
    PipelineHealth,
    QueryDistributionEntry,
    ResponseTimeSeriesPoint,
)

DEFAULT_WINDOW_DAYS = 30

_METHOD_FIELD = {
    SearchType.EXACT_TEXT: "exact_text_ms",
    SearchType.SEMANTIC: "semantic_ms",
    SearchType.SPEECH_TO_TEXT: "speech_to_text_ms",
}


def resolve_date_range(
    date_from: datetime.date | None, date_to: datetime.date | None
) -> tuple[datetime.date, datetime.date]:
    """Fills in a default window when a bound is missing; raises ValueError if from > to."""
    today = datetime.date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        date_from = date_to - datetime.timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if date_from > date_to:
        raise ValueError("date_from must not be after date_to.")
    return date_from, date_to


def _previous_period(date_from: datetime.date, date_to: datetime.date) -> tuple[datetime.date, datetime.date]:
    duration = (date_to - date_from) + datetime.timedelta(days=1)
    previous_to = date_from - datetime.timedelta(days=1)
    previous_from = previous_to - duration + datetime.timedelta(days=1)
    return previous_from, previous_to


def _bounds(date_from: datetime.date, date_to: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    # [start, end) is half-open so date_to's whole calendar day is included.
    start = datetime.datetime.combine(date_from, datetime.time.min)
    end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min)
    return start, end


def _kpi(current: float | int, previous: float | int | None) -> KpiValue:
    if previous is None or previous == 0:
        return KpiValue(value=current, delta_percent=None, previous_value=previous)
    delta_percent = ((current - previous) / previous) * 100
    return KpiValue(value=current, delta_percent=round(delta_percent, 1), previous_value=previous)


def _query_count(db: Session, start: datetime.datetime, end: datetime.datetime) -> int:
    return (
        db.query(func.count(SearchQuery.id))
        .filter(SearchQuery.created_at >= start, SearchQuery.created_at < end)
        .scalar()
        or 0
    )


def _avg_response_time_ms(db: Session, start: datetime.datetime, end: datetime.datetime) -> float | None:
    result = (
        db.query(func.avg(SearchQuery.response_time_ms))
        .filter(
            SearchQuery.created_at >= start,
            SearchQuery.created_at < end,
            SearchQuery.response_time_ms.isnot(None),
        )
        .scalar()
    )
    return float(result) if result is not None else None


def _ready_media_count(db: Session, start: datetime.datetime, end: datetime.datetime) -> int:
    return (
        db.query(func.count(Video.id))
        .filter(Video.status == MediaStatus.READY, Video.uploaded_at >= start, Video.uploaded_at < end)
        .scalar()
        or 0
    )


def _failed_uploads_count(db: Session, start: datetime.datetime, end: datetime.datetime) -> int:
    return (
        db.query(func.count(Video.id))
        .filter(Video.status == MediaStatus.FAILED, Video.uploaded_at >= start, Video.uploaded_at < end)
        .scalar()
        or 0
    )


def _transcript_segments_count(db: Session, start: datetime.datetime, end: datetime.datetime) -> int:
    return (
        db.query(func.count(TranscriptSegment.id))
        .join(Video, Video.id == TranscriptSegment.video_id)
        .filter(Video.uploaded_at >= start, Video.uploaded_at < end)
        .scalar()
        or 0
    )


def _clips_created_count(db: Session, start: datetime.datetime, end: datetime.datetime) -> int:
    return (
        db.query(func.count(GeneratedClip.id))
        .filter(GeneratedClip.created_at >= start, GeneratedClip.created_at < end)
        .scalar()
        or 0
    )


def _response_time_series(
    db: Session, start: datetime.datetime, end: datetime.datetime
) -> list[ResponseTimeSeriesPoint]:
    rows = (
        db.query(
            func.date(SearchQuery.created_at).label("day"),
            SearchQuery.query_type,
            func.avg(SearchQuery.response_time_ms).label("avg_ms"),
        )
        .filter(
            SearchQuery.created_at >= start,
            SearchQuery.created_at < end,
            SearchQuery.response_time_ms.isnot(None),
        )
        .group_by("day", SearchQuery.query_type)
        .order_by("day")
        .all()
    )

    by_day: dict[datetime.date, dict[str, float]] = {}
    for day, query_type, avg_ms in rows:
        # func.date() may return a string depending on the driver, so coerce defensively.
        day_value = day if isinstance(day, datetime.date) else datetime.date.fromisoformat(str(day))
        by_day.setdefault(day_value, {})[_METHOD_FIELD[query_type]] = round(float(avg_ms), 1)

    return [
        ResponseTimeSeriesPoint(date=day, **values)
        for day, values in sorted(by_day.items())
    ]


def _query_distribution(db: Session, start: datetime.datetime, end: datetime.datetime) -> list[QueryDistributionEntry]:
    rows = (
        db.query(SearchQuery.query_type, func.count(SearchQuery.id))
        .filter(SearchQuery.created_at >= start, SearchQuery.created_at < end)
        .group_by(SearchQuery.query_type)
        .all()
    )
    total = sum(count for _type, count in rows)
    if total == 0:
        return []
    return [
        QueryDistributionEntry(search_type=query_type, count=count, percent=round(count / total * 100, 1))
        for query_type, count in rows
    ]


def build_usage_insight(distribution: list[QueryDistributionEntry], best_accuracy_method: SearchType | None) -> str | None:
    """Builds a deterministic sentence from real usage/accuracy data only, never a fabricated claim."""
    if not distribution:
        return None
    top = max(distribution, key=lambda e: e.count)
    top_label = _SEARCH_TYPE_LABEL[top.search_type]
    if best_accuracy_method is None:
        return f"{top_label} is currently the most-used search method."
    if best_accuracy_method == top.search_type:
        return f"{top_label} is both the most-used and the highest-accuracy search method."
    best_label = _SEARCH_TYPE_LABEL[best_accuracy_method]
    return f"{top_label} is used the most, while {best_label} currently has the highest measured accuracy."


_SEARCH_TYPE_LABEL = {
    SearchType.EXACT_TEXT: "Exact Text Search",
    SearchType.SEMANTIC: "Semantic Search",
    SearchType.SPEECH_TO_TEXT: "Speech-to-Text",
}


def get_operational_analytics(
    db: Session, date_from: datetime.date, date_to: datetime.date, best_accuracy_method: SearchType | None = None
) -> OperationalAnalyticsOut:
    """Entry point called by the router; best_accuracy_method is optional evaluation data used only for the usage insight text."""
    start, end = _bounds(date_from, date_to)
    prev_from, prev_to = _previous_period(date_from, date_to)
    prev_start, prev_end = _bounds(prev_from, prev_to)

    total_queries = _query_count(db, start, end)
    prev_total_queries = _query_count(db, prev_start, prev_end)

    avg_response = _avg_response_time_ms(db, start, end)
    prev_avg_response = _avg_response_time_ms(db, prev_start, prev_end)

    media_indexed = _ready_media_count(db, start, end)
    prev_media_indexed = _ready_media_count(db, prev_start, prev_end)

    distribution = _query_distribution(db, start, end)

    usage_insight = build_usage_insight(distribution, best_accuracy_method)

    return OperationalAnalyticsOut(
        date_from=date_from,
        date_to=date_to,
        search_accuracy=None,  # populated by the router from evaluation_service, not here
        average_response_time_ms=_kpi(avg_response or 0.0, prev_avg_response),
        media_files_indexed=_kpi(media_indexed, prev_media_indexed),
        queries_processed=_kpi(total_queries, prev_total_queries),
        response_time_series=_response_time_series(db, start, end),
        query_distribution=distribution,
        total_queries=total_queries,
        pipeline_health=PipelineHealth(
            media_processed=media_indexed,
            transcript_segments_generated=_transcript_segments_count(db, start, end),
            clips_created=_clips_created_count(db, start, end),
            failed_uploads=_failed_uploads_count(db, start, end),
        ),
        usage_insight=usage_insight,
    )
