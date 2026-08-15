"""Evaluation runs a frozen set of EvaluationTestCase rows against either the real PostgreSQL retrieval path (search_service.execute_search, the same function real search calls) or the Elasticsearch evaluation index, writing results to evaluation_results only so operational analytics stays unaffected. Precision/Recall are defined against a single expected video+timestamp per test case; see PRECISION_RECALL_DEFINITION."""

from __future__ import annotations

import datetime
import time

from sqlalchemy.orm import Session

from app.enums import SearchBackend
from app.models.evaluation_result import EvaluationResult
from app.models.evaluation_test_case import EvaluationTestCase
from app.models.user import User
from app.schemas.analytics import EvaluationAnalyticsOut, EvaluationSummaryOut, MethodEvaluationRow
from app.schemas.search import SearchRequest
from app.services import elasticsearch_service, search_service

PRECISION_RECALL_DEFINITION = (
    "Single-relevant-item retrieval: each EvaluationTestCase names exactly "
    "one expected video + timestamp window. Precision@K = 1/K if that item "
    "appears anywhere in the top K results, else 0/K. Recall@K = 1.0 if "
    "found in the top K, else 0.0 (there is exactly one known relevant "
    "item, so recall is binary by construction, not averaged over multiple "
    "relevant documents)."
)


# Re-exported for router convenience; defined once in elasticsearch_service.py.
ElasticsearchUnavailableError = elasticsearch_service.ElasticsearchUnavailableError


def _is_correct(video_id: int, start_time: float | None, end_time: float | None, test_case: EvaluationTestCase) -> bool:
    if video_id != test_case.expected_video_id:
        return False
    if start_time is None:
        return False
    tol = test_case.timestamp_tolerance_seconds
    lo = test_case.expected_start_time - tol
    hi = test_case.expected_end_time + tol
    # Half-open overlap, matching match_resolver.py's overlap convention.
    result_end = end_time if end_time is not None else start_time
    return start_time < hi and result_end > lo


def _compute_metrics(
    test_case: EvaluationTestCase, ranked: list[tuple[int, float | None, float | None]], k: int
) -> tuple[bool, float, float, float, float]:
    """ranked: [(video_id, start_time, end_time), ...] in rank order,
    already limited to top K by the caller. Returns
    (is_correct, accuracy, precision_at_k, recall_at_k, reciprocal_rank)."""
    first_correct_rank = None
    for rank, (video_id, start_time, end_time) in enumerate(ranked, start=1):
        if _is_correct(video_id, start_time, end_time, test_case):
            first_correct_rank = rank
            break

    is_correct = first_correct_rank is not None
    accuracy = 1.0 if is_correct else 0.0
    precision_at_k = (1.0 / k) if is_correct else 0.0
    recall_at_k = 1.0 if is_correct else 0.0
    reciprocal_rank = (1.0 / first_correct_rank) if first_correct_rank else 0.0
    return is_correct, accuracy, precision_at_k, recall_at_k, reciprocal_rank


def run_test_case(
    db: Session, admin: User, test_case: EvaluationTestCase, search_backend: SearchBackend, result_limit: int = 20
) -> EvaluationResult:
    """Executes one test case against one backend and persists the resulting EvaluationResult row. Raises ElasticsearchUnavailableError if the ES client can't be reached."""
    if search_backend == SearchBackend.ELASTICSEARCH:
        started = time.perf_counter()
        es_result = elasticsearch_service.evaluate_query(
            db,
            query_text=test_case.query_text or "",
            limit=result_limit,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked = es_result.ranked_video_windows
        top_result_id = None  # Elasticsearch evaluation results aren't SearchResult rows
        search_query_id = None
        response_time_ms = elapsed_ms
    else:
        if not test_case.query_text:
            raise ValueError("This test case has no query_text; only text/semantic test cases are supported here.")
        request = SearchRequest(
            query_text=test_case.query_text,
            query_type=test_case.search_type,
            search_scope=test_case.search_scope,
            limit=result_limit,
        )
        response = search_service.execute_search(db, admin, request)
        ranked = [(r.video_id, r.matched_start_time, r.matched_end_time) for r in response.results]
        search_query_id = response.search_query_id
        response_time_ms = response.response_time_ms
        top_result_id = response.results[0].result_id if response.results else None

    is_correct, accuracy, precision_at_k, recall_at_k, reciprocal_rank = _compute_metrics(
        test_case, ranked, result_limit
    )

    result = EvaluationResult(
        test_case_id=test_case.id,
        search_query_id=search_query_id,
        top_result_id=top_result_id,
        search_backend=search_backend,
        is_correct=is_correct,
        accuracy_score=accuracy,
        precision_at_k=precision_at_k,
        recall_at_k=recall_at_k,
        reciprocal_rank=reciprocal_rank,
        response_time_ms=response_time_ms,
        evaluated_at=datetime.datetime.utcnow(),
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def run_test_cases(
    db: Session,
    admin: User,
    search_backend: SearchBackend,
    test_case_id: int | None = None,
    result_limit: int = 20,
) -> list[EvaluationResult]:
    """Runs every EvaluationTestCase (or just test_case_id if given). A single ElasticsearchUnavailableError aborts the whole batch immediately."""
    query = db.query(EvaluationTestCase)
    if test_case_id is not None:
        query = query.filter(EvaluationTestCase.id == test_case_id)
    test_cases = query.order_by(EvaluationTestCase.id.asc()).all()

    results = []
    for test_case in test_cases:
        if test_case.query_text is None:
            # Audio-query test cases aren't supported by this runner yet; skipped, not counted as a failure.
            continue
        result = run_test_case(db, admin, test_case, search_backend, result_limit)
        results.append(result)
    return results


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def get_evaluation_analytics(
    db: Session,
    search_backend: SearchBackend,
    date_from: datetime.date,
    date_to: datetime.date,
) -> EvaluationAnalyticsOut:
    """Aggregates persisted EvaluationResult rows for the requested backend and date range. Returns backend_available=False when Elasticsearch isn't reachable, kept distinct from the zero-results case."""
    if search_backend == SearchBackend.ELASTICSEARCH and not elasticsearch_service.is_available():
        return EvaluationAnalyticsOut(
            search_backend=search_backend,
            date_from=date_from,
            date_to=date_to,
            backend_available=False,
            unavailable_reason="Elasticsearch evaluation is not configured yet.",
            overall_accuracy=None,
            method_rows=[],
            summary=None,
            evaluated_test_case_count=0,
            last_run_at=None,
        )

    start = datetime.datetime.combine(date_from, datetime.time.min)
    end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min)

    rows = (
        db.query(EvaluationResult, EvaluationTestCase.search_type)
        .join(EvaluationTestCase, EvaluationTestCase.id == EvaluationResult.test_case_id)
        .filter(
            EvaluationResult.search_backend == search_backend,
            EvaluationResult.evaluated_at >= start,
            EvaluationResult.evaluated_at < end,
        )
        .all()
    )

    if not rows:
        reason = (
            None
            if search_backend == SearchBackend.POSTGRESQL
            else "No Elasticsearch evaluation results are available for this period."
        )
        return EvaluationAnalyticsOut(
            search_backend=search_backend,
            date_from=date_from,
            date_to=date_to,
            backend_available=True,
            unavailable_reason=reason,
            overall_accuracy=None,
            method_rows=[],
            summary=None,
            evaluated_test_case_count=0,
            last_run_at=None,
        )

    by_type: dict = {}
    for result, search_type in rows:
        by_type.setdefault(search_type, []).append(result)

    method_rows: list[MethodEvaluationRow] = []
    for search_type, results in by_type.items():
        accuracy = sum(r.accuracy_score or 0.0 for r in results) / len(results)
        precision = sum(r.precision_at_k or 0.0 for r in results) / len(results)
        recall = sum(r.recall_at_k or 0.0 for r in results) / len(results)
        method_rows.append(
            MethodEvaluationRow(
                search_type=search_type,
                accuracy=round(accuracy, 3),
                precision=round(precision, 3),
                recall=round(recall, 3),
                f1=round(_f1(precision, recall) or 0.0, 3),
                sample_count=len(results),
            )
        )

    overall_accuracy = sum(r.accuracy_score or 0.0 for r, _ in rows) / len(rows)
    last_run_at = max(r.evaluated_at for r, _ in rows)

    best_performing = max(method_rows, key=lambda r: r.f1 or 0.0)
    highest_accuracy = max(method_rows, key=lambda r: r.accuracy or 0.0)
    fastest_by_type: dict = {}
    for result, search_type in rows:
        if result.response_time_ms is None:
            continue
        fastest_by_type.setdefault(search_type, []).append(result.response_time_ms)
    fastest_method = (
        min(fastest_by_type, key=lambda t: sum(fastest_by_type[t]) / len(fastest_by_type[t]))
        if fastest_by_type
        else None
    )

    summary = EvaluationSummaryOut(
        best_performing_method=best_performing.search_type,
        best_performing_note=f"Highest F1 score for the {search_backend.value} backend this period.",
        highest_accuracy_method=highest_accuracy.search_type,
        highest_accuracy_note=f"Highest measured accuracy for the {search_backend.value} backend this period.",
        fastest_method=fastest_method,
        fastest_note="Lowest average evaluation response time this period." if fastest_method else None,
    )

    return EvaluationAnalyticsOut(
        search_backend=search_backend,
        date_from=date_from,
        date_to=date_to,
        backend_available=True,
        unavailable_reason=None,
        overall_accuracy=round(overall_accuracy, 3),
        method_rows=method_rows,
        summary=summary,
        evaluated_test_case_count=len(rows),
        last_run_at=last_run_at,
    )
