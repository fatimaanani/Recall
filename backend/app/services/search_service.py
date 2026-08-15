"""Typed-text search (execute_search) runs exactly one retrieval branch chosen by query_type. Speech-to-Text search (execute_speech_to_text_search) is the only caller that runs both branches and blends them via merge_and_rank, since a transcribed query has no explicit method choice behind it."""

from __future__ import annotations

import dataclasses
import pathlib
import time
import uuid

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import MediaStatus, MediaVisibility, SearchScope, SearchType
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.processing import embedding_processor, whisper_processor
from app.processing.ffmpeg_processor import ProcessingError
from app.schemas.search import SearchRequest, SearchResponse, SearchResultCategoryBrief, SearchResultOut
from app.services import error_log_service
from app.utils.file_validation import ALLOWED_AUDIO_EXTENSIONS, UnsupportedFileTypeError, validate_upload


class EmptyQueryTextError(Exception):
    pass


class UnsupportedSearchMethodError(Exception):
    pass


class SemanticEmbeddingError(Exception):
    pass


class RetrievalError(Exception):
    pass


class InvalidQueryAudioError(Exception):
    """Unsupported extension or a magic-byte signature mismatch."""


class QueryAudioTooLargeError(Exception):
    """Exceeds settings.query_audio_max_size_bytes."""


class QueryTranscriptionError(Exception):
    """FFmpeg extraction or Whisper transcription itself failed/timed out."""


class EmptyTranscriptionError(Exception):
    """Transcription produced no usable text; rejected rather than searched as empty."""


# No role branch: MY_LIBRARY/BOTH can only ever match Video.owner_id == user.id, so
# "no admin bypass into another user's private uploads" is true by construction.
def _scope_predicate(user: User, scope):
    if scope.value == "my_library":
        return Video.owner_id == user.id
    if scope.value == "shared_library":
        return Video.visibility == MediaVisibility.SHARED
    # BOTH
    return or_(Video.owner_id == user.id, Video.visibility == MediaVisibility.SHARED)


# Raw match, one row from one retrieval branch, before normalization/merge.
# Exactly one of raw_keyword_rank / raw_cosine_distance is set, depending
# on which branch produced it.
@dataclasses.dataclass
class _RawMatch:
    transcript_segment_id: int
    video: Video
    start_time: float
    end_time: float
    text: str
    raw_keyword_rank: float | None = None
    raw_cosine_distance: float | None = None


# websearch_to_tsquery never raises on malformed input, unlike plainto_tsquery (no phrase
# support) or raw to_tsquery. 'simple' config must match the indexed tsvector's config exactly,
# or nothing would match.
def _run_exact_text_search(db: Session, user: User, scope, query_text: str, limit: int) -> list[_RawMatch]:
    tsquery = func.websearch_to_tsquery("simple", query_text)
    rank = func.ts_rank(TranscriptSegment.search_vector, tsquery)
    rows = (
        db.query(TranscriptSegment, Video, rank)
        .join(Video, TranscriptSegment.video_id == Video.id)
        .filter(
            Video.status == MediaStatus.READY,
            _scope_predicate(user, scope),
            TranscriptSegment.search_vector.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
        .all()
    )
    return [
        _RawMatch(
            transcript_segment_id=segment.id,
            video=video,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text,
            raw_keyword_rank=float(raw_rank),
        )
        for segment, video, raw_rank in rows
    ]


# cosine_distance compiles to Postgres's <=> operator. has_embeddings and embedding.isnot(None)
# are checked together as a defensive double-check against the two ever disagreeing.
def _run_semantic_search(db: Session, user: User, scope, query_text: str, limit: int) -> list[_RawMatch]:
    # Raises ProcessingError on failure, mapped by the caller to SemanticEmbeddingError; reuses
    # the same process-wide model singleton media_processing_service.py uses.
    query_vector = embedding_processor.generate_embeddings([query_text])[0]

    distance = TranscriptSegment.embedding.cosine_distance(query_vector)
    rows = (
        db.query(TranscriptSegment, Video, distance)
        .join(Video, TranscriptSegment.video_id == Video.id)
        .filter(
            Video.status == MediaStatus.READY,
            _scope_predicate(user, scope),
            Video.has_embeddings.is_(True),
            TranscriptSegment.embedding.isnot(None),
        )
        .order_by(distance.asc())
        .limit(limit)
        .all()
    )
    return [
        _RawMatch(
            transcript_segment_id=segment.id,
            video=video,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text,
            raw_cosine_distance=float(raw_distance),
        )
        for segment, video, raw_distance in rows
    ]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# ts_rank isn't bounded to a fixed range, so normalize per-query against this branch's own max
# rather than a fixed formula.
def _normalize_keyword_scores(matches: list[_RawMatch]) -> dict[int, float]:
    if not matches:
        return {}
    max_rank = max(m.raw_keyword_rank for m in matches)
    if max_rank <= 0:
        # Defensive only; the @@ filter already excludes non-matches, but never divide by zero.
        return {m.transcript_segment_id: 0.0 for m in matches}
    return {m.transcript_segment_id: _clamp01(m.raw_keyword_rank / max_rank) for m in matches}


# Cosine distance is mathematically bounded to [0, 2] regardless of query, so no per-query
# normalization is needed; clamped anyway for floating-point safety.
def _normalize_semantic_scores(matches: list[_RawMatch]) -> dict[int, float]:
    return {m.transcript_segment_id: _clamp01(1 - (m.raw_cosine_distance / 2)) for m in matches}


# confidence_score/keyword_score/semantic_score are all in their final, normalized form.
@dataclasses.dataclass
class MergedResult:
    transcript_segment_id: int
    video: Video
    start_time: float
    end_time: float
    text: str
    confidence_score: float
    keyword_score: float | None
    semantic_score: float | None


# General two-branch merger; typed-text search populates one branch, speech-to-text populates both.
def merge_and_rank(
    keyword_matches: list[_RawMatch],
    semantic_matches: list[_RawMatch],
    keyword_weight: float,
    semantic_weight: float,
    limit: int,
) -> list[MergedResult]:
    normalized_keyword = _normalize_keyword_scores(keyword_matches)
    normalized_semantic = _normalize_semantic_scores(semantic_matches)

    # Segment metadata is identical regardless of branch (same underlying row), so one lookup
    # built from both lists suffices.
    segment_lookup: dict[int, _RawMatch] = {}
    for match in keyword_matches:
        segment_lookup[match.transcript_segment_id] = match
    for match in semantic_matches:
        segment_lookup.setdefault(match.transcript_segment_id, match)

    merged: list[MergedResult] = []
    for segment_id, match in segment_lookup.items():
        k_score = normalized_keyword.get(segment_id)
        s_score = normalized_semantic.get(segment_id)

        # A single-populated branch's confidence_score equals that branch's own normalized score
        # exactly; the unused score stays None.
        if k_score is not None and s_score is not None:
            confidence = keyword_weight * k_score + semantic_weight * s_score
        elif k_score is not None:
            confidence = k_score
        elif s_score is not None:
            confidence = s_score
        else:
            confidence = 0.0  # unreachable in practice, defensive only

        merged.append(
            MergedResult(
                transcript_segment_id=segment_id,
                video=match.video,
                start_time=match.start_time,
                end_time=match.end_time,
                text=match.text,
                # Final clamp guards against float rounding and a hybrid weight pair that doesn't
                # sum to 1 pushing the blend outside [0, 1].
                confidence_score=_clamp01(confidence),
                keyword_score=k_score,
                semantic_score=s_score,
            )
        )

    # Deterministic tie-break: confidence DESC, then keyword, then semantic (None sorts last),
    # then transcript_segment_id ASC.
    merged.sort(
        key=lambda r: (
            -r.confidence_score,
            -(r.keyword_score if r.keyword_score is not None else -1.0),
            -(r.semantic_score if r.semantic_score is not None else -1.0),
            r.transcript_segment_id,
        )
    )

    return merged[:limit]


# One transaction: builds the SearchQuery and every SearchResult, flushes once to get real ids,
# then commits once; any SQLAlchemyError rolls back the whole thing.
def _persist_and_build_response(
    db: Session,
    user: User,
    query_type: SearchType,
    search_scope: SearchScope,
    query_text: str,
    keyword_matches: list[_RawMatch],
    semantic_matches: list[_RawMatch],
    limit: int,
    started_at: float,
    transcribed_text: str | None = None,
    original_audio_filename: str | None = None,
) -> SearchResponse:
    settings = get_settings()

    merged = merge_and_rank(
        keyword_matches, semantic_matches,
        settings.hybrid_keyword_weight, settings.hybrid_semantic_weight,
        limit,
    )

    # Measures retrieval + ranking only, not the persistence write below. For Speech-to-Text,
    # started_at is taken after transcription finishes, since that's a separate cost.
    response_time_ms = (time.perf_counter() - started_at) * 1000

    search_query = SearchQuery(
        user_id=user.id,
        query_text=query_text,
        query_type=query_type,
        search_scope=search_scope,
        results_found=len(merged),
        response_time_ms=response_time_ms,
        transcribed_text=transcribed_text,
        original_audio_filename=original_audio_filename,
    )
    db.add(search_query)

    rows: list[tuple[SearchResult, Video]] = []
    for position, item in enumerate(merged, start=1):
        # Assigned via the relationship, not a literal query_id, since search_query has no id
        # yet at this point (not flushed) -- SQLAlchemy orders the INSERTs and synchronizes
        # query_id once it's known.
        result = SearchResult(
            query=search_query,
            video_id=item.video.id,
            transcript_segment_id=item.transcript_segment_id,
            matched_start_time=item.start_time,
            matched_end_time=item.end_time,
            matched_text=item.text,
            confidence_score=item.confidence_score,
            keyword_score=item.keyword_score,
            semantic_score=item.semantic_score,
            rank_position=position,
        )
        db.add(result)
        rows.append((result, item.video))

    try:
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        raise

    results_out = [
        SearchResultOut(
            result_id=result.id,
            rank_position=result.rank_position,
            video_id=video.id,
            video_title=video.title,
            transcript_segment_id=result.transcript_segment_id,
            matched_start_time=result.matched_start_time,
            matched_end_time=result.matched_end_time,
            matched_text=result.matched_text,
            confidence_score=result.confidence_score,
            keyword_score=result.keyword_score,
            semantic_score=result.semantic_score,
            has_thumbnail=video.thumbnail_path is not None,
            library="my_library" if video.owner_id == user.id else "shared_library",
            # Same convention as app/schemas/video.py's video_to_out.
            media_type="video" if video.mime_type.startswith("video/") else "audio",
            categories=[
                SearchResultCategoryBrief(id=link.category.id, name=link.category.name)
                for link in video.category_links
            ],
            video_uploaded_at=video.uploaded_at,
            video_file_size_bytes=video.file_size_bytes,
        )
        for result, video in rows
    ]

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(search_query)

    return SearchResponse(
        search_query_id=search_query.id,
        query_text=query_text,
        query_type=query_type,
        search_scope=search_scope,
        response_time_ms=response_time_ms,
        result_count=len(results_out),
        results=results_out,
        transcribed_text=transcribed_text,
    )


# Exactly one retrieval branch, chosen by request.query_type.
def execute_search(db: Session, user: User, request: SearchRequest) -> SearchResponse:
    query_text = request.query_text.strip()
    if not query_text:
        raise EmptyQueryTextError()

    if request.query_type == SearchType.SPEECH_TO_TEXT:
        raise UnsupportedSearchMethodError()

    started_at = time.perf_counter()

    keyword_matches: list[_RawMatch] = []
    semantic_matches: list[_RawMatch] = []

    if request.query_type == SearchType.EXACT_TEXT:
        try:
            keyword_matches = _run_exact_text_search(db, user, request.search_scope, query_text, request.limit)
        except SQLAlchemyError as exc:
            error_log_service.log_error(db, error_source="exact_text_search", error_message=str(exc), user_id=user.id)
            raise RetrievalError("Exact-text search failed.") from exc
    elif request.query_type == SearchType.SEMANTIC:
        try:
            semantic_matches = _run_semantic_search(db, user, request.search_scope, query_text, request.limit)
        except ProcessingError as exc:
            error_log_service.log_error(db, error_source="semantic_search", error_message=str(exc), user_id=user.id)
            raise SemanticEmbeddingError(str(exc)) from exc
        except SQLAlchemyError as exc:
            error_log_service.log_error(db, error_source="semantic_search", error_message=str(exc), user_id=user.id)
            raise RetrievalError("Semantic search failed.") from exc

    return _persist_and_build_response(
        db, user, request.query_type, request.search_scope, query_text,
        keyword_matches, semantic_matches, request.limit, started_at,
    )


# Validates audio, transcribes via Whisper, retrieves via both branches, persists, then always
# deletes the temp audio files (finally block below) once written.
def execute_speech_to_text_search(
    db: Session,
    user: User,
    audio_bytes: bytes,
    original_filename: str,
    search_scope: SearchScope,
    limit: int,
) -> SearchResponse:
    settings = get_settings()

    if len(audio_bytes) > settings.query_audio_max_size_bytes:
        raise QueryAudioTooLargeError(
            f"Query audio exceeds the {settings.query_audio_max_size_bytes}-byte limit."
        )

    # Reuses the same allow-list and magic-byte check every media upload goes through,
    # restricted to audio extensions only since this is a search query, not a media upload.
    try:
        extension, _mime_type = validate_upload(original_filename, audio_bytes[:64])
    except UnsupportedFileTypeError as exc:
        raise InvalidQueryAudioError(str(exc)) from exc
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise InvalidQueryAudioError(
            f"'.{extension}' is not an accepted query-audio format. "
            f"Use one of: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}."
        )

    # Server-generated temp filenames; never trust the client's original filename as a filesystem path.
    temp_dir = pathlib.Path(settings.processing_temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    raw_audio_path = temp_dir / f"{uuid.uuid4().hex}.{extension}"
    wav_path = temp_dir / f"{uuid.uuid4().hex}.wav"

    try:
        raw_audio_path.write_bytes(audio_bytes)

        try:
            whisper_processor.extract_audio(raw_audio_path, wav_path)
            segments = whisper_processor.transcribe_audio(
                wav_path, timeout_seconds=settings.query_transcription_timeout_seconds
            )
        except ProcessingError as exc:
            error_log_service.log_error(db, error_source="speech_query_transcription", error_message=str(exc), user_id=user.id)
            raise QueryTranscriptionError(str(exc)) from exc

        # Same evaluate_segment/is_hallucination_dominated helpers the uploaded-media pipeline
        # uses, so a query is held to the same reliability bar. Segments are joined into one
        # string since there's no TranscriptSegment row for a search query.
        reliable_segments = [s for s in segments if whisper_processor.evaluate_segment(s)[0]]
        if not reliable_segments or whisper_processor.is_hallucination_dominated(reliable_segments):
            raise EmptyTranscriptionError(
                "No reliable speech detected in this audio. Try again with a clearer recording."
            )

        transcribed_text = " ".join(s.text.strip() for s in reliable_segments).strip()
        if not transcribed_text:
            raise EmptyTranscriptionError(
                "No reliable speech detected in this audio. Try again with a clearer recording."
            )

        # Retrieval timing starts here, after transcription, since that's Whisper's cost.
        started_at = time.perf_counter()

        try:
            keyword_matches = _run_exact_text_search(db, user, search_scope, transcribed_text, limit)
        except SQLAlchemyError as exc:
            error_log_service.log_error(db, error_source="exact_text_search", error_message=str(exc), user_id=user.id)
            raise RetrievalError("Exact-text search failed.") from exc

        try:
            semantic_matches = _run_semantic_search(db, user, search_scope, transcribed_text, limit)
        except ProcessingError as exc:
            error_log_service.log_error(db, error_source="semantic_search", error_message=str(exc), user_id=user.id)
            raise SemanticEmbeddingError(str(exc)) from exc
        except SQLAlchemyError as exc:
            error_log_service.log_error(db, error_source="semantic_search", error_message=str(exc), user_id=user.id)
            raise RetrievalError("Semantic search failed.") from exc

        return _persist_and_build_response(
            db, user, SearchType.SPEECH_TO_TEXT, search_scope, transcribed_text,
            keyword_matches, semantic_matches, limit, started_at,
            transcribed_text=transcribed_text,
            original_audio_filename=original_filename,
        )
    finally:
        # audio_query_path is deliberately never persisted, since these files won't exist once deleted.
        raw_audio_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
