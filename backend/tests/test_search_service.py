"""
test_search_service.py

1. Shared helpers
2. Unit tests -- scope predicate (compiled-SQL assertions, no DB)
3. Unit tests -- hybrid merge/normalize/rank (synthetic _RawMatch inputs)
4. Unit tests -- execute_search orchestration (mocked DB + mocked retrieval)
5. Unit tests -- request/response schema validation
6. Integration tests -- real PostgreSQL + pgvector (TEST_DATABASE_URL)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.enums import (
    MediaSourceType,
    MediaStatus,
    MediaVisibility,
    SearchScope,
    SearchType,
    SubtitleSource,
    UserRole,
)
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.processing.ffmpeg_processor import ProcessingError
from app.schemas.search import SearchRequest
from app.services import search_service


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _make_user(**overrides) -> User:
    defaults = dict(
        id=1,
        full_name="Test User",
        username="testuser",
        email="test@example.com",
        password_hash="not-a-real-hash",
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_video(**overrides) -> Video:
    defaults = dict(
        id=1,
        owner_id=1,
        title="Test video",
        original_filename="test.mp4",
        file_path="videos/1/test.mp4",
        file_size_bytes=1024,
        mime_type="video/mp4",
        status=MediaStatus.READY,
        source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
        has_embeddings=False,
    )
    defaults.update(overrides)
    return Video(**defaults)


def _make_segment(**overrides) -> TranscriptSegment:
    defaults = dict(
        id=1,
        video_id=1,
        start_time=0.0,
        end_time=2.0,
        text="hello world",
        source=SubtitleSource.WHISPER,
    )
    defaults.update(overrides)
    return TranscriptSegment(**defaults)


def _make_raw_match(**overrides) -> search_service._RawMatch:
    defaults = dict(
        transcript_segment_id=1,
        video=_make_video(),
        start_time=0.0,
        end_time=2.0,
        text="hello world",
    )
    defaults.update(overrides)
    return search_service._RawMatch(**defaults)


# Mock DB session that actually simulates id-assignment on flush, so
# execute_search's post-flush SearchResultOut construction (which needs
# real ids) works against a mock the same way it would against a real
# session -- captures every db.add()-ed object and assigns incrementing
# ids to whichever ones don't have one yet, the first time flush() runs.
def _make_mock_db():
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append

    def _flush():
        next_id = 1
        for obj in added:
            if getattr(obj, "id", None) is None:
                obj.id = next_id
            next_id = obj.id + 1

    mock_db.flush.side_effect = _flush
    mock_db.commit.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: None
    mock_db._added = added
    return mock_db


# ===========================================================================
# 2. Unit tests -- scope predicate (compiled-SQL assertions, no DB)
# ===========================================================================

def test_scope_predicate_my_library_filters_by_owner():
    user = _make_user(id=7)
    compiled = str(search_service._scope_predicate(user, SearchScope.MY_LIBRARY))
    assert "videos.owner_id" in compiled
    assert "visibility" not in compiled


def test_scope_predicate_shared_library_filters_by_visibility():
    user = _make_user(id=7)
    compiled = str(search_service._scope_predicate(user, SearchScope.SHARED_LIBRARY))
    assert "videos.visibility" in compiled
    assert "owner_id" not in compiled


def test_scope_predicate_both_is_owner_or_shared():
    user = _make_user(id=7)
    compiled = str(search_service._scope_predicate(user, SearchScope.BOTH))
    assert "videos.owner_id" in compiled
    assert "videos.visibility" in compiled
    assert " OR " in compiled


# ===========================================================================
# 3. Unit tests -- hybrid merge/normalize/rank (synthetic _RawMatch inputs)
# ===========================================================================

def test_merge_and_rank_exact_only_confidence_equals_normalized_keyword():
    matches = [
        _make_raw_match(transcript_segment_id=1, raw_keyword_rank=0.5),
        _make_raw_match(transcript_segment_id=2, raw_keyword_rank=0.25),
    ]
    results = search_service.merge_and_rank(matches, [], 0.5, 0.5, limit=10)

    assert len(results) == 2
    top, second = results
    assert top.transcript_segment_id == 1
    assert top.keyword_score == 1.0  # normalized against its own branch's max
    assert top.semantic_score is None
    assert top.confidence_score == top.keyword_score  # approved single-branch rule
    assert second.keyword_score == 0.5


def test_merge_and_rank_semantic_only_confidence_equals_normalized_semantic():
    matches = [
        _make_raw_match(transcript_segment_id=1, raw_cosine_distance=0.0),  # identical -> similarity 1.0
        _make_raw_match(transcript_segment_id=2, raw_cosine_distance=1.0),  # -> similarity 0.5
    ]
    results = search_service.merge_and_rank([], matches, 0.5, 0.5, limit=10)

    assert len(results) == 2
    top, second = results
    assert top.transcript_segment_id == 1
    assert top.semantic_score == 1.0
    assert top.keyword_score is None
    assert top.confidence_score == top.semantic_score
    assert second.semantic_score == 0.5


def test_merge_and_rank_merges_duplicate_segment_from_both_branches():
    keyword_matches = [_make_raw_match(transcript_segment_id=1, raw_keyword_rank=1.0)]
    semantic_matches = [_make_raw_match(transcript_segment_id=1, raw_cosine_distance=0.0)]

    results = search_service.merge_and_rank(keyword_matches, semantic_matches, 0.5, 0.5, limit=10)

    assert len(results) == 1  # merged into one row, not two
    merged = results[0]
    assert merged.keyword_score == 1.0
    assert merged.semantic_score == 1.0
    assert merged.confidence_score == pytest.approx(0.5 * 1.0 + 0.5 * 1.0)


def test_merge_and_rank_deterministic_tie_break_by_segment_id():
    # Both segments tie on every score -- final tiebreak must be
    # transcript_segment_id ascending.
    matches = [
        _make_raw_match(transcript_segment_id=5, raw_keyword_rank=1.0),
        _make_raw_match(transcript_segment_id=2, raw_keyword_rank=1.0),
        _make_raw_match(transcript_segment_id=9, raw_keyword_rank=1.0),
    ]
    results = search_service.merge_and_rank(matches, [], 0.5, 0.5, limit=10)
    assert [r.transcript_segment_id for r in results] == [2, 5, 9]


def test_merge_and_rank_respects_limit_after_merge():
    matches = [_make_raw_match(transcript_segment_id=i, raw_keyword_rank=float(i)) for i in range(1, 6)]
    results = search_service.merge_and_rank(matches, [], 0.5, 0.5, limit=2)
    assert len(results) == 2
    assert results[0].transcript_segment_id == 5  # highest raw rank first


def test_merge_and_rank_no_matches_returns_empty_list():
    assert search_service.merge_and_rank([], [], 0.5, 0.5, limit=10) == []


def test_normalize_semantic_scores_clamps_to_zero_one():
    # cosine_distance can range up to 2 -- similarity formula must stay in [0, 1]
    matches = [
        _make_raw_match(transcript_segment_id=1, raw_cosine_distance=2.0),  # similarity -1 -> clamped to 0
        _make_raw_match(transcript_segment_id=2, raw_cosine_distance=-0.0001),  # tiny float noise -> clamped to 1
    ]
    normalized = search_service._normalize_semantic_scores(matches)
    assert normalized[1] == 0.0
    assert normalized[2] == 1.0


def test_normalize_keyword_scores_per_query_min_max():
    matches = [
        _make_raw_match(transcript_segment_id=1, raw_keyword_rank=0.8),
        _make_raw_match(transcript_segment_id=2, raw_keyword_rank=0.4),
        _make_raw_match(transcript_segment_id=3, raw_keyword_rank=0.8),
    ]
    normalized = search_service._normalize_keyword_scores(matches)
    assert normalized[1] == 1.0
    assert normalized[3] == 1.0
    assert normalized[2] == 0.5


# ===========================================================================
# 4. Unit tests -- execute_search orchestration (mocked DB + mocked retrieval)
# ===========================================================================

def test_execute_search_exact_text_persists_and_returns_response(mocker):
    user = _make_user()
    video = _make_video(id=3, owner_id=user.id, title="Lecture 1")
    mock_db = _make_mock_db()

    mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[
            search_service._RawMatch(
                transcript_segment_id=10, video=video, start_time=1.0, end_time=3.0,
                text="hello world", raw_keyword_rank=0.9,
            )
        ],
    )

    request = SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT)
    response = search_service.execute_search(mock_db, user, request)

    assert response.query_type == SearchType.EXACT_TEXT
    assert response.result_count == 1
    assert response.results[0].keyword_score == 1.0
    assert response.results[0].semantic_score is None
    assert response.results[0].library == "my_library"
    assert response.results[0].rank_position == 1
    # media_type/video_file_size_bytes derived from the already-loaded
    # Video row; categories empty since this mock video has no
    # category_links; video_uploaded_at is None here because this Video
    # object was constructed directly, never flushed (its DB-side default
    # only applies on a real INSERT) -- see SearchResultOut's own comment.
    assert response.results[0].media_type == "video"
    assert response.results[0].video_file_size_bytes == 1024
    assert response.results[0].categories == []
    assert response.results[0].video_uploaded_at is None
    mock_db.commit.assert_called_once()

    # Persisted rows: one SearchQuery, one SearchResult.
    persisted_queries = [obj for obj in mock_db._added if isinstance(obj, SearchQuery)]
    persisted_results = [obj for obj in mock_db._added if isinstance(obj, SearchResult)]
    assert len(persisted_queries) == 1
    assert persisted_queries[0].results_found == 1
    assert len(persisted_results) == 1
    assert persisted_results[0].matched_text == "hello world"


def test_execute_search_result_out_maps_video_metadata_fields(mocker):
    # Dedicated test for SearchResultOut's derived fields: audio
    # mime_type -> media_type="audio", a
    # populated category_links -> categories, and a real uploaded_at.
    import datetime as dt

    from app.models.category import Category
    from app.models.video_category import VideoCategory

    user = _make_user()
    video = _make_video(
        id=7, owner_id=user.id, title="Lecture Audio", mime_type="audio/mpeg",
        file_size_bytes=2048,
    )
    video.uploaded_at = dt.datetime(2026, 8, 1, 12, 0, 0)
    category = Category(id=5, user_id=user.id, name="University")
    link = VideoCategory(video_id=video.id, category_id=category.id)
    link.category = category
    video.category_links = [link]

    mock_db = _make_mock_db()
    mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[
            search_service._RawMatch(
                transcript_segment_id=20, video=video, start_time=0.0, end_time=2.0,
                text="audio segment", raw_keyword_rank=0.5,
            )
        ],
    )

    request = SearchRequest(query_text="audio segment", query_type=SearchType.EXACT_TEXT)
    response = search_service.execute_search(mock_db, user, request)

    result_out = response.results[0]
    assert result_out.media_type == "audio"
    assert result_out.video_file_size_bytes == 2048
    assert result_out.video_uploaded_at == dt.datetime(2026, 8, 1, 12, 0, 0)
    assert len(result_out.categories) == 1
    assert result_out.categories[0].id == 5
    assert result_out.categories[0].name == "University"


def test_execute_search_semantic_uses_semantic_branch_only(mocker):
    user = _make_user()
    video = _make_video(id=3, owner_id=99)  # shared, not owned by this user
    video.visibility = MediaVisibility.SHARED
    mock_db = _make_mock_db()

    mocker.patch.object(
        search_service, "_run_semantic_search",
        return_value=[
            search_service._RawMatch(
                transcript_segment_id=11, video=video, start_time=0.0, end_time=1.0,
                text="matching text", raw_cosine_distance=0.2,
            )
        ],
    )

    request = SearchRequest(query_text="a paraphrase", query_type=SearchType.SEMANTIC)
    response = search_service.execute_search(mock_db, user, request)

    assert response.results[0].keyword_score is None
    assert response.results[0].semantic_score is not None
    assert response.results[0].library == "shared_library"


def test_execute_search_rejects_speech_to_text():
    user = _make_user()
    mock_db = _make_mock_db()
    request = SearchRequest(query_text="some audio transcript", query_type=SearchType.SPEECH_TO_TEXT)

    with pytest.raises(search_service.UnsupportedSearchMethodError):
        search_service.execute_search(mock_db, user, request)
    mock_db.add.assert_not_called()


def test_execute_search_rejects_whitespace_only_query(mocker):
    user = _make_user()
    mock_db = _make_mock_db()
    # Bypass SearchRequest's own validation to exercise the service-layer
    # trim check directly (min_length=1 alone would accept "   ").
    request = SearchRequest.model_construct(
        query_text="   ", query_type=SearchType.EXACT_TEXT, search_scope=SearchScope.BOTH, limit=20
    )

    with pytest.raises(search_service.EmptyQueryTextError):
        search_service.execute_search(mock_db, user, request)
    mock_db.add.assert_not_called()


def test_execute_search_zero_results_still_persists_query(mocker):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(search_service, "_run_exact_text_search", return_value=[])

    request = SearchRequest(query_text="nothing matches this", query_type=SearchType.EXACT_TEXT)
    response = search_service.execute_search(mock_db, user, request)

    assert response.result_count == 0
    assert response.results == []
    persisted_queries = [obj for obj in mock_db._added if isinstance(obj, SearchQuery)]
    assert len(persisted_queries) == 1
    assert persisted_queries[0].results_found == 0
    mock_db.commit.assert_called_once()


def test_execute_search_wraps_sqlalchemy_error_as_retrieval_error(mocker):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(
        search_service, "_run_exact_text_search", side_effect=SQLAlchemyError("db exploded")
    )

    request = SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT)
    with pytest.raises(search_service.RetrievalError):
        search_service.execute_search(mock_db, user, request)
    # No SearchQuery/SearchResult row was ever staged -- failed before
    # _persist_and_build_response runs. error_log_service.log_error
    # (2026-08-08) does stage exactly one row (the ErrorLog itself), which
    # is the behavior under test here, not a regression -- see
    # test_search_error_logging.py for the dedicated logging assertions.
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1


def test_execute_search_wraps_processing_error_as_semantic_embedding_error(mocker):
    user = _make_user()
    mock_db = _make_mock_db()
    mocker.patch.object(
        search_service, "_run_semantic_search", side_effect=ProcessingError("model unavailable")
    )

    request = SearchRequest(query_text="hello", query_type=SearchType.SEMANTIC)
    with pytest.raises(search_service.SemanticEmbeddingError):
        search_service.execute_search(mock_db, user, request)
    added_error_logs = [obj for obj in mock_db._added if type(obj).__name__ == "ErrorLog"]
    assert len(added_error_logs) == 1


def test_execute_search_rolls_back_on_flush_failure(mocker):
    user = _make_user()
    video = _make_video()
    mock_db = _make_mock_db()
    mock_db.flush.side_effect = SQLAlchemyError("constraint violation")
    mocker.patch.object(
        search_service, "_run_exact_text_search",
        return_value=[search_service._RawMatch(
            transcript_segment_id=1, video=video, start_time=0.0, end_time=1.0,
            text="x", raw_keyword_rank=1.0,
        )],
    )

    request = SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT)
    with pytest.raises(SQLAlchemyError):
        search_service.execute_search(mock_db, user, request)
    mock_db.rollback.assert_called_once()
    mock_db.commit.assert_not_called()


# ===========================================================================
# 5. Unit tests -- request/response schema validation
# ===========================================================================

def test_search_request_rejects_empty_query_text():
    with pytest.raises(ValidationError):
        SearchRequest(query_text="", query_type=SearchType.EXACT_TEXT)


def test_search_request_accepts_whitespace_only_at_schema_level():
    # Documents the deliberate split: Pydantic only checks non-empty
    # length, the service layer (tested above) rejects trimmed-empty text.
    request = SearchRequest(query_text="   ", query_type=SearchType.EXACT_TEXT)
    assert request.query_text == "   "


def test_search_request_rejects_limit_out_of_range():
    with pytest.raises(ValidationError):
        SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT, limit=0)
    with pytest.raises(ValidationError):
        SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT, limit=101)


def test_search_request_rejects_invalid_query_type():
    with pytest.raises(ValidationError):
        SearchRequest(query_text="hello", query_type="not_a_real_method")


def test_search_request_accepts_speech_to_text_at_schema_level():
    # Valid SearchType enum member -- schema-level acceptance is
    # deliberate (it's a real, generally-valid SearchType value); rejection
    # is search_service.execute_search's job, not the schema's, since it's
    # a current-implementation-scope rule, not a type-validation rule.
    request = SearchRequest(query_text="hello", query_type=SearchType.SPEECH_TO_TEXT)
    assert request.query_type == SearchType.SPEECH_TO_TEXT


def test_search_request_default_scope_is_both():
    request = SearchRequest(query_text="hello", query_type=SearchType.EXACT_TEXT)
    assert request.search_scope == SearchScope.BOTH


# ===========================================================================
# 6. Integration tests -- real PostgreSQL + pgvector (TEST_DATABASE_URL)
# ===========================================================================

def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(full_name="Test User", username=f"searchuser{id(overrides)}", email=f"search{id(overrides)}@example.com", password_hash="x")
    defaults.update(overrides)
    user = User(**defaults)
    pg_session.add(user)
    pg_session.flush()
    return user


def _pg_make_video(pg_session, owner_id, **overrides) -> Video:
    defaults = dict(
        owner_id=owner_id, title="Video", original_filename="v.mp4",
        file_path=f"videos/{owner_id}/v.mp4", file_size_bytes=1024, mime_type="video/mp4",
        status=MediaStatus.READY, source_type=MediaSourceType.USER_UPLOAD,
        visibility=MediaVisibility.PRIVATE,
    )
    defaults.update(overrides)
    video = Video(**defaults)
    pg_session.add(video)
    pg_session.flush()
    return video


def _pg_make_segment(pg_session, video_id, text, **overrides) -> TranscriptSegment:
    defaults = dict(video_id=video_id, start_time=0.0, end_time=2.0, text=text, source=SubtitleSource.WHISPER)
    defaults.update(overrides)
    segment = TranscriptSegment(**defaults)
    pg_session.add(segment)
    pg_session.flush()
    return segment


def test_search_vector_generated_column_populates_automatically_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="genuser1", email="gen1@example.com")
    video = _pg_make_video(pg_session, user.id)
    segment = _pg_make_segment(pg_session, video.id, "the quick brown fox")
    pg_session.commit()

    pg_session.refresh(segment)
    assert segment.search_vector is not None  # populated with no application code touching it


def test_mixed_language_fts_finds_english_and_arabic_segments_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="mixuser", email="mix@example.com")
    video = _pg_make_video(pg_session, user.id)
    english_segment = _pg_make_segment(pg_session, video.id, "welcome to the lecture today")
    arabic_segment = _pg_make_segment(pg_session, video.id, "مرحبا بكم في المحاضرة اليوم")
    mixed_segment = _pg_make_segment(pg_session, video.id, "welcome مرحبا to the lecture")
    pg_session.commit()

    english_matches = search_service._run_exact_text_search(
        pg_session, user, SearchScope.BOTH, "lecture", limit=10
    )
    matched_ids = {m.transcript_segment_id for m in english_matches}
    assert english_segment.id in matched_ids
    assert mixed_segment.id in matched_ids
    assert arabic_segment.id not in matched_ids

    arabic_matches = search_service._run_exact_text_search(
        pg_session, user, SearchScope.BOTH, "مرحبا", limit=10
    )
    arabic_matched_ids = {m.transcript_segment_id for m in arabic_matches}
    assert arabic_segment.id in arabic_matched_ids
    assert mixed_segment.id in arabic_matched_ids
    assert english_segment.id not in arabic_matched_ids


def test_exact_search_ranks_higher_match_density_first_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="rankuser", email="rank@example.com")
    video = _pg_make_video(pg_session, user.id)
    weak_match = _pg_make_segment(pg_session, video.id, "python is mentioned once here")
    strong_match = _pg_make_segment(pg_session, video.id, "python python python everywhere python")
    pg_session.commit()

    matches = search_service._run_exact_text_search(pg_session, user, SearchScope.BOTH, "python", limit=10)
    assert matches[0].transcript_segment_id == strong_match.id
    assert matches[0].raw_keyword_rank > matches[1].raw_keyword_rank
    assert matches[1].transcript_segment_id == weak_match.id


def test_semantic_search_orders_by_similarity_in_postgres(pg_session, mocker):
    user = _pg_make_user(pg_session, username="semuser", email="sem@example.com")
    video = _pg_make_video(pg_session, user.id, has_embeddings=True)
    near_vector = [1.0] + [0.0] * 383
    far_vector = [0.0, 1.0] + [0.0] * 382
    near_segment = _pg_make_segment(pg_session, video.id, "near", embedding=near_vector)
    far_segment = _pg_make_segment(pg_session, video.id, "far", embedding=far_vector)
    pg_session.commit()

    mocker.patch.object(search_service.embedding_processor, "generate_embeddings", return_value=[near_vector])

    matches = search_service._run_semantic_search(pg_session, user, SearchScope.BOTH, "query text", limit=10)
    assert matches[0].transcript_segment_id == near_segment.id
    assert matches[1].transcript_segment_id == far_segment.id
    assert matches[0].raw_cosine_distance < matches[1].raw_cosine_distance


def test_scope_filtering_my_library_shared_library_both_in_postgres(pg_session):
    user_a = _pg_make_user(pg_session, username="scopeuserA", email="scopeA@example.com")
    user_b = _pg_make_user(pg_session, username="scopeuserB", email="scopeB@example.com")

    private_a = _pg_make_video(pg_session, user_a.id, visibility=MediaVisibility.PRIVATE)
    shared_video = _pg_make_video(pg_session, user_b.id, visibility=MediaVisibility.SHARED)
    private_b = _pg_make_video(pg_session, user_b.id, visibility=MediaVisibility.PRIVATE)

    seg_private_a = _pg_make_segment(pg_session, private_a.id, "keyword alpha")
    seg_shared = _pg_make_segment(pg_session, shared_video.id, "keyword alpha")
    seg_private_b = _pg_make_segment(pg_session, private_b.id, "keyword alpha")
    pg_session.commit()

    my_library = {m.transcript_segment_id for m in search_service._run_exact_text_search(
        pg_session, user_a, SearchScope.MY_LIBRARY, "alpha", limit=10)}
    assert my_library == {seg_private_a.id}

    shared_library = {m.transcript_segment_id for m in search_service._run_exact_text_search(
        pg_session, user_a, SearchScope.SHARED_LIBRARY, "alpha", limit=10)}
    assert shared_library == {seg_shared.id}

    both = {m.transcript_segment_id for m in search_service._run_exact_text_search(
        pg_session, user_a, SearchScope.BOTH, "alpha", limit=10)}
    assert both == {seg_private_a.id, seg_shared.id}
    assert seg_private_b.id not in both  # user A never sees user B's private video


def test_ready_only_filtering_excludes_processing_video_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="readyuser", email="ready@example.com")
    processing_video = _pg_make_video(pg_session, user.id, status=MediaStatus.PROCESSING)
    _pg_make_segment(pg_session, processing_video.id, "keyword beta")
    pg_session.commit()

    matches = search_service._run_exact_text_search(pg_session, user, SearchScope.BOTH, "beta", limit=10)
    assert matches == []


def test_admin_personal_upload_appears_in_my_library_and_shared_library_in_postgres(pg_session):
    admin = _pg_make_user(pg_session, username="adminuser", email="admin@example.com", role=UserRole.ADMIN)
    admin_video = _pg_make_video(
        pg_session, admin.id,
        source_type=MediaSourceType.ADMIN_PRELOADED, visibility=MediaVisibility.SHARED,
    )
    _pg_make_segment(pg_session, admin_video.id, "keyword gamma")
    pg_session.commit()

    my_library = search_service._run_exact_text_search(pg_session, admin, SearchScope.MY_LIBRARY, "gamma", limit=10)
    shared_library = search_service._run_exact_text_search(pg_session, admin, SearchScope.SHARED_LIBRARY, "gamma", limit=10)
    assert len(my_library) == 1
    assert len(shared_library) == 1
    assert my_library[0].transcript_segment_id == shared_library[0].transcript_segment_id


def test_execute_search_persists_query_and_result_rows_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="persistuser", email="persist@example.com")
    video = _pg_make_video(pg_session, user.id, title="Persistence Test Video")
    _pg_make_segment(pg_session, video.id, "keyword delta appears here")
    pg_session.commit()

    request = SearchRequest(query_text="delta", query_type=SearchType.EXACT_TEXT)
    response = search_service.execute_search(pg_session, user, request)

    assert response.result_count == 1
    persisted_query = pg_session.query(SearchQuery).filter(SearchQuery.id == response.search_query_id).one()
    assert persisted_query.results_found == 1
    assert persisted_query.query_text == "delta"

    persisted_results = pg_session.query(SearchResult).filter(SearchResult.query_id == persisted_query.id).all()
    assert len(persisted_results) == 1
    assert persisted_results[0].matched_text == "keyword delta appears here"
    assert persisted_results[0].rank_position == 1


def test_execute_search_zero_result_query_persisted_in_postgres(pg_session):
    user = _pg_make_user(pg_session, username="zerouser", email="zero@example.com")
    request = SearchRequest(query_text="nothing will ever match this exact phrase", query_type=SearchType.EXACT_TEXT)

    response = search_service.execute_search(pg_session, user, request)

    assert response.result_count == 0
    persisted_query = pg_session.query(SearchQuery).filter(SearchQuery.id == response.search_query_id).one()
    assert persisted_query.results_found == 0
