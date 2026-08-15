"""Elasticsearch is an evaluation-only backend: it is never used by real user search and exists only to run the same evaluation test cases PostgreSQL FTS runs, so the two can be compared. This module is never imported by search_service.py/search.py, keeping it physically separate from real search."""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import MediaStatus
from app.models.transcript_segment import TranscriptSegment
from app.models.video import Video


class ElasticsearchUnavailableError(Exception):
    """Elasticsearch is disabled, unconfigured, or unreachable; always surfaced as an honest "unavailable" response, never silently replaced with PostgreSQL numbers."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class EsEvaluationResult:
    """Return shape for evaluate_query; an internal value, not a Pydantic schema serialized to clients."""

    def __init__(self, ranked_video_windows: list[tuple[int, float | None, float | None]]):
        self.ranked_video_windows = ranked_video_windows


_client = None
_client_init_attempted = False


def _get_client():
    """Lazy singleton; only constructed when actually needed, so a missing Elasticsearch can never break app startup."""
    global _client, _client_init_attempted
    if _client is not None:
        return _client
    if _client_init_attempted:
        raise ElasticsearchUnavailableError("Elasticsearch client previously failed to initialize.")
    _client_init_attempted = True

    settings = get_settings()
    if not settings.elasticsearch_enabled:
        raise ElasticsearchUnavailableError("Elasticsearch evaluation is not configured yet.")

    try:
        from elasticsearch import Elasticsearch
    except ImportError as exc:
        raise ElasticsearchUnavailableError(
            "The elasticsearch Python client is not installed."
        ) from exc

    kwargs: dict = {"hosts": [settings.elasticsearch_url], "request_timeout": settings.elasticsearch_timeout_seconds}
    if settings.elasticsearch_username and settings.elasticsearch_password:
        kwargs["basic_auth"] = (settings.elasticsearch_username, settings.elasticsearch_password)

    client = Elasticsearch(**kwargs)
    try:
        if not client.ping():
            raise ElasticsearchUnavailableError("Elasticsearch did not respond to a ping at ELASTICSEARCH_URL.")
    except ElasticsearchUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 -- any transport/connection error is "unavailable" here, not a crash
        raise ElasticsearchUnavailableError(f"Could not connect to Elasticsearch: {exc}") from exc

    _client = client
    return _client


def is_available() -> bool:
    """Health-check-friendly boolean wrapper around _get_client(); never raises."""
    try:
        _get_client()
        return True
    except ElasticsearchUnavailableError:
        return False


_MAPPING = {
    "properties": {
        "segment_id": {"type": "integer"},
        "video_id": {"type": "integer"},
        "text": {"type": "text"},
        "start_time": {"type": "float"},
        "end_time": {"type": "float"},
        "owner_id": {"type": "integer"},
        "visibility": {"type": "keyword"},
        "video_status": {"type": "keyword"},
    }
}


def ensure_index() -> None:
    """Creates the evaluation index with its mapping if it doesn't already exist; idempotent."""
    settings = get_settings()
    client = _get_client()
    if not client.indices.exists(index=settings.elasticsearch_index_name):
        client.indices.create(index=settings.elasticsearch_index_name, mappings=_MAPPING)


def _segment_to_document(segment: TranscriptSegment, video: Video) -> dict:
    return {
        "segment_id": segment.id,
        "video_id": video.id,
        "text": segment.text,
        "start_time": segment.start_time,
        "end_time": segment.end_time,
        "owner_id": video.owner_id,
        "visibility": video.visibility.value,
        "video_status": video.status.value,
    }


def index_segment(segment: TranscriptSegment, video: Video) -> None:
    """Upserts one segment keyed by its own id, so reprocessing a video's segments doesn't accumulate stale documents."""
    settings = get_settings()
    client = _get_client()
    client.index(index=settings.elasticsearch_index_name, id=segment.id, document=_segment_to_document(segment, video))


def delete_segment(segment_id: int) -> None:
    settings = get_settings()
    client = _get_client()
    try:
        client.delete(index=settings.elasticsearch_index_name, id=segment_id, ignore=[404])
    except Exception as exc:  # noqa: BLE001
        raise ElasticsearchUnavailableError(f"Could not delete document {segment_id}: {exc}") from exc


def backfill(db: Session) -> int:
    """Indexes every READY video's transcript segments. Admin-triggered only, never part of the live upload pipeline. Returns the number of documents indexed."""
    ensure_index()
    count = 0
    segments = (
        db.query(TranscriptSegment)
        .join(Video, Video.id == TranscriptSegment.video_id)
        .filter(Video.status == MediaStatus.READY)
        .all()
    )
    for segment in segments:
        index_segment(segment, segment.video)
        count += 1
    return count


def document_count() -> int:
    settings = get_settings()
    client = _get_client()
    return client.count(index=settings.elasticsearch_index_name)["count"]


def evaluate_query(db: Session, query_text: str, limit: int = 20) -> EsEvaluationResult:
    """Runs a query against the Elasticsearch evaluation index via a `match` query on `text`, ranked by Elasticsearch's relevance score. Not scoped by user, since evaluation has no per-case "run as" concept."""
    settings = get_settings()
    client = _get_client()
    response = client.search(
        index=settings.elasticsearch_index_name,
        query={"match": {"text": query_text}},
        size=limit,
    )
    hits = response["hits"]["hits"]
    ranked = [
        (hit["_source"]["video_id"], hit["_source"]["start_time"], hit["_source"]["end_time"])
        for hit in hits
    ]
    return EsEvaluationResult(ranked_video_windows=ranked)
