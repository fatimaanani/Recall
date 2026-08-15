"""
test_evaluation_service.py

1. Shared pg_* helpers
2. Pure unit tests -- _is_correct (in-memory EvaluationTestCase, no DB)
3. Pure unit tests -- _compute_metrics / _f1
4. Integration (pg_session) -- run_test_case against the real PostgreSQL
   retrieval path (search_service.execute_search)
5. Integration -- run_test_cases skips audio-only test cases
6. Integration -- get_evaluation_analytics aggregation, no-data honesty,
   date filtering, and PostgreSQL/Elasticsearch backend isolation
"""

from __future__ import annotations

import datetime

import pytest

from app.enums import (
    MediaSourceType,
    MediaStatus,
    MediaVisibility,
    SearchBackend,
    SearchScope,
    SearchType,
    SubtitleSource,
)
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_test_case import EvaluationTestCase
from app.models.transcript_segment import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.services import evaluation_service

# ===========================================================================
# 1. Shared pg_* helpers
# ===========================================================================


def _pg_make_user(pg_session, **overrides) -> User:
    defaults = dict(
        full_name="Test User", username=f"evaluser{id(overrides)}",
        email=f"eval{id(overrides)}@example.com", password_hash="x",
    )
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
    defaults = dict(video_id=video_id, start_time=10.0, end_time=15.0, text=text, source=SubtitleSource.WHISPER)
    defaults.update(overrides)
    segment = TranscriptSegment(**defaults)
    pg_session.add(segment)
    pg_session.flush()
    return segment


def _pg_make_test_case(pg_session, expected_video_id, **overrides) -> EvaluationTestCase:
    defaults = dict(
        test_name="Test case", query_text="recursion example", search_type=SearchType.EXACT_TEXT,
        search_scope=SearchScope.BOTH, expected_video_id=expected_video_id,
        expected_start_time=10.0, expected_end_time=15.0, timestamp_tolerance_seconds=5.0,
    )
    defaults.update(overrides)
    test_case = EvaluationTestCase(**defaults)
    pg_session.add(test_case)
    pg_session.flush()
    return test_case


def _pg_make_evaluation_result(pg_session, test_case_id, **overrides) -> EvaluationResult:
    defaults = dict(
        test_case_id=test_case_id, search_backend=SearchBackend.POSTGRESQL, is_correct=True,
        accuracy_score=1.0, precision_at_k=0.5, recall_at_k=1.0, reciprocal_rank=1.0,
        response_time_ms=50.0, evaluated_at=datetime.datetime.utcnow(),
    )
    defaults.update(overrides)
    result = EvaluationResult(**defaults)
    pg_session.add(result)
    pg_session.flush()
    return result


def _make_test_case(**overrides) -> EvaluationTestCase:
    """In-memory only, no DB -- for pure-function tests of _is_correct /
    _compute_metrics, which only ever read attributes off the object."""
    defaults = dict(
        id=1, test_name="tc", query_text="q", search_type=SearchType.EXACT_TEXT,
        search_scope=SearchScope.BOTH, expected_video_id=7,
        expected_start_time=100.0, expected_end_time=110.0, timestamp_tolerance_seconds=5.0,
    )
    defaults.update(overrides)
    return EvaluationTestCase(**defaults)


def _day(offset: int) -> datetime.datetime:
    anchor = datetime.datetime(2026, 6, 15, 12, 0, 0)
    return anchor + datetime.timedelta(days=offset)


# ===========================================================================
# 2. Pure unit tests -- _is_correct
# ===========================================================================


def test_is_correct_true_when_video_and_window_match_within_tolerance():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0, timestamp_tolerance_seconds=5.0)
    assert evaluation_service._is_correct(7, 102.0, 108.0, tc) is True


def test_is_correct_false_when_video_id_does_not_match():
    tc = _make_test_case(expected_video_id=7)
    assert evaluation_service._is_correct(8, 102.0, 108.0, tc) is False


def test_is_correct_false_when_window_is_outside_tolerance():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0, timestamp_tolerance_seconds=5.0)
    # Result window [200, 210] does not overlap [95, 115] at all
    assert evaluation_service._is_correct(7, 200.0, 210.0, tc) is False


def test_is_correct_false_when_start_time_is_none():
    tc = _make_test_case(expected_video_id=7)
    assert evaluation_service._is_correct(7, None, None, tc) is False


def test_is_correct_true_at_the_edge_of_tolerance_window():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0, timestamp_tolerance_seconds=5.0)
    # Tolerant window is [95, 115); a result starting just inside it overlaps
    assert evaluation_service._is_correct(7, 114.0, 120.0, tc) is True


# ===========================================================================
# 3. Pure unit tests -- _compute_metrics / _f1
# ===========================================================================


def test_compute_metrics_correct_at_rank_one():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0)
    ranked = [(7, 102.0, 108.0), (9, 500.0, 505.0)]
    is_correct, accuracy, precision, recall, rr = evaluation_service._compute_metrics(tc, ranked, k=2)
    assert is_correct is True
    assert accuracy == 1.0
    assert precision == pytest.approx(0.5)  # 1/k, k=2
    assert recall == 1.0
    assert rr == 1.0  # 1/rank, rank=1


def test_compute_metrics_correct_at_rank_three():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0)
    ranked = [(1, 1.0, 2.0), (2, 3.0, 4.0), (7, 102.0, 108.0)]
    is_correct, accuracy, precision, recall, rr = evaluation_service._compute_metrics(tc, ranked, k=3)
    assert is_correct is True
    assert rr == pytest.approx(1.0 / 3.0)
    assert precision == pytest.approx(1.0 / 3.0)


def test_compute_metrics_no_correct_result_in_ranked_list():
    tc = _make_test_case(expected_video_id=7, expected_start_time=100.0, expected_end_time=110.0)
    ranked = [(1, 1.0, 2.0), (2, 3.0, 4.0)]
    is_correct, accuracy, precision, recall, rr = evaluation_service._compute_metrics(tc, ranked, k=2)
    assert is_correct is False
    assert accuracy == 0.0
    assert precision == 0.0
    assert recall == 0.0
    assert rr == 0.0


def test_f1_harmonic_mean_of_precision_and_recall():
    assert evaluation_service._f1(0.5, 1.0) == pytest.approx(2 * 0.5 * 1.0 / 1.5)


def test_f1_is_zero_not_none_when_both_precision_and_recall_are_zero():
    assert evaluation_service._f1(0.0, 0.0) == 0.0


def test_f1_is_none_when_a_metric_is_not_computed():
    assert evaluation_service._f1(None, 1.0) is None
    assert evaluation_service._f1(0.5, None) is None


# ===========================================================================
# 4. Integration -- run_test_case against the real PostgreSQL retrieval path
# ===========================================================================


def test_run_test_case_persists_a_correct_postgresql_result_via_real_search(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin1", email="evaladmin1@example.com")
    video = _pg_make_video(pg_session, admin.id)
    _pg_make_segment(pg_session, video.id, "an explanation of merge sort complexity", start_time=10.0, end_time=15.0)
    pg_session.commit()

    test_case = _pg_make_test_case(
        pg_session, video.id, query_text="merge sort complexity",
        expected_start_time=10.0, expected_end_time=15.0, timestamp_tolerance_seconds=5.0,
    )
    pg_session.commit()

    result = evaluation_service.run_test_case(pg_session, admin, test_case, SearchBackend.POSTGRESQL, result_limit=10)

    assert result.search_backend == SearchBackend.POSTGRESQL
    assert result.is_correct is True
    assert result.accuracy_score == 1.0
    assert result.search_query_id is not None  # reused the real search path, a real SearchQuery row exists

    persisted = pg_session.query(EvaluationResult).filter(EvaluationResult.id == result.id).one()
    assert persisted.test_case_id == test_case.id


def test_run_test_case_records_incorrect_when_expected_video_never_matches(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin2", email="evaladmin2@example.com")
    wrong_video = _pg_make_video(pg_session, admin.id)
    _pg_make_segment(pg_session, wrong_video.id, "completely unrelated content about cooking")
    pg_session.commit()

    # expected_video_id points at a video that will never appear in results
    # for this query text (its only segment does not contain the phrase)
    other_video = _pg_make_video(pg_session, admin.id)
    test_case = _pg_make_test_case(
        pg_session, other_video.id, query_text="completely unrelated content about cooking",
        expected_start_time=999.0, expected_end_time=999.0,
    )
    pg_session.commit()

    result = evaluation_service.run_test_case(pg_session, admin, test_case, SearchBackend.POSTGRESQL, result_limit=10)
    assert result.is_correct is False
    assert result.accuracy_score == 0.0


# ===========================================================================
# 5. Integration -- run_test_cases skips audio-only test cases
# ===========================================================================


def test_run_test_cases_skips_audio_only_test_cases_without_erroring(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin3", email="evaladmin3@example.com")
    video = _pg_make_video(pg_session, admin.id)
    _pg_make_segment(pg_session, video.id, "a lecture about graph traversal")
    pg_session.commit()

    text_case = _pg_make_test_case(pg_session, video.id, query_text="graph traversal", expected_start_time=10.0, expected_end_time=15.0)
    audio_case = _pg_make_test_case(
        pg_session, video.id, query_text=None, audio_query_path="query_audio/sample.wav",
        search_type=SearchType.SPEECH_TO_TEXT,
    )
    pg_session.commit()

    results = evaluation_service.run_test_cases(pg_session, admin, SearchBackend.POSTGRESQL, result_limit=10)
    ran_test_case_ids = {r.test_case_id for r in results}
    assert text_case.id in ran_test_case_ids
    assert audio_case.id not in ran_test_case_ids  # skipped, not errored or miscounted


# ===========================================================================
# 6. Integration -- get_evaluation_analytics
# ===========================================================================


def test_get_evaluation_analytics_returns_honest_no_data_state_for_postgresql(pg_session):
    far_future = datetime.date(2099, 1, 1)
    out = evaluation_service.get_evaluation_analytics(pg_session, SearchBackend.POSTGRESQL, far_future, far_future)
    assert out.backend_available is True  # PostgreSQL itself is always available
    assert out.method_rows == []
    assert out.summary is None
    assert out.overall_accuracy is None
    assert out.evaluated_test_case_count == 0


def test_get_evaluation_analytics_elasticsearch_unavailable_by_default():
    # elasticsearch_enabled defaults to False -- must never attempt a
    # connection or crash, just report the honest unavailable state.
    out = evaluation_service.get_evaluation_analytics(
        None, SearchBackend.ELASTICSEARCH, datetime.date(2026, 6, 1), datetime.date(2026, 6, 30)
    )
    assert out.backend_available is False
    assert out.unavailable_reason == "Elasticsearch evaluation is not configured yet."
    assert out.method_rows == []


def test_get_evaluation_analytics_aggregates_real_persisted_results(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin4", email="evaladmin4@example.com")
    video = _pg_make_video(pg_session, admin.id)
    test_case = _pg_make_test_case(pg_session, video.id, search_type=SearchType.EXACT_TEXT)
    pg_session.commit()

    _pg_make_evaluation_result(
        pg_session, test_case.id, search_backend=SearchBackend.POSTGRESQL,
        accuracy_score=1.0, precision_at_k=1.0, recall_at_k=1.0, response_time_ms=40.0,
        evaluated_at=_day(0),
    )
    _pg_make_evaluation_result(
        pg_session, test_case.id, search_backend=SearchBackend.POSTGRESQL,
        accuracy_score=0.0, precision_at_k=0.0, recall_at_k=0.0, response_time_ms=60.0,
        evaluated_at=_day(0),
    )
    pg_session.commit()

    out = evaluation_service.get_evaluation_analytics(
        pg_session, SearchBackend.POSTGRESQL, _day(0).date(), _day(0).date()
    )
    assert out.evaluated_test_case_count == 2
    assert out.overall_accuracy == pytest.approx(0.5)
    row = next(r for r in out.method_rows if r.search_type == SearchType.EXACT_TEXT)
    assert row.accuracy == pytest.approx(0.5)
    assert row.sample_count == 2
    assert out.summary is not None
    assert out.summary.highest_accuracy_method == SearchType.EXACT_TEXT


def test_get_evaluation_analytics_excludes_rows_outside_the_date_window(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin5", email="evaladmin5@example.com")
    video = _pg_make_video(pg_session, admin.id)
    test_case = _pg_make_test_case(pg_session, video.id)
    pg_session.commit()

    _pg_make_evaluation_result(pg_session, test_case.id, evaluated_at=_day(-10))  # outside window
    pg_session.commit()

    out = evaluation_service.get_evaluation_analytics(
        pg_session, SearchBackend.POSTGRESQL, _day(0).date(), _day(0).date()
    )
    assert out.evaluated_test_case_count == 0
    assert out.method_rows == []


def test_get_evaluation_analytics_never_mixes_postgresql_and_elasticsearch_rows(pg_session):
    admin = _pg_make_user(pg_session, username="evaladmin6", email="evaladmin6@example.com")
    video = _pg_make_video(pg_session, admin.id)
    test_case = _pg_make_test_case(pg_session, video.id)
    pg_session.commit()

    _pg_make_evaluation_result(pg_session, test_case.id, search_backend=SearchBackend.POSTGRESQL, evaluated_at=_day(0))
    _pg_make_evaluation_result(pg_session, test_case.id, search_backend=SearchBackend.ELASTICSEARCH, evaluated_at=_day(0))
    pg_session.commit()

    out = evaluation_service.get_evaluation_analytics(
        pg_session, SearchBackend.POSTGRESQL, _day(0).date(), _day(0).date()
    )
    # Only the PostgreSQL-backend row counted, even though an Elasticsearch
    # row exists for the same test case on the same day -- the two
    # dimensions must never be mixed into one aggregate.
    assert out.evaluated_test_case_count == 1
