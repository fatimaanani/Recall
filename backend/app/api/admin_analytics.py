from __future__ import annotations

import csv
import datetime
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_admin
from app.enums import SearchBackend
from app.models.evaluation_test_case import EvaluationTestCase
from app.models.user import User
from app.models.video import Video
from app.schemas.analytics import EvaluationAnalyticsOut, OperationalAnalyticsOut
from app.schemas.evaluation import (
    EvaluationTestCaseCreate,
    EvaluationTestCaseOut,
    RunEvaluationRequest,
    RunEvaluationResponse,
)
from app.services import analytics_service, elasticsearch_service, error_log_service, evaluation_service

router = APIRouter(prefix="/api/admin", tags=["admin-analytics"])


def _resolve_range(date_from: datetime.date | None, date_to: datetime.date | None) -> tuple[datetime.date, datetime.date]:
    try:
        return analytics_service.resolve_date_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/analytics/overview", response_model=OperationalAnalyticsOut)
def get_analytics_overview(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> OperationalAnalyticsOut:
    resolved_from, resolved_to = _resolve_range(date_from, date_to)

    # Only used for the usage-insight sentence; overview's own numbers stay
    # independent of the evaluation backend toggle.
    evaluation = evaluation_service.get_evaluation_analytics(
        db, SearchBackend.POSTGRESQL, resolved_from, resolved_to
    )
    best_accuracy_method = (
        evaluation.summary.highest_accuracy_method if evaluation.summary else None
    )

    overview = analytics_service.get_operational_analytics(db, resolved_from, resolved_to, best_accuracy_method)
    overview.search_accuracy = None  # see /analytics/evaluation for the toggle-aware Search Accuracy KPI
    return overview


@router.get("/analytics/evaluation", response_model=EvaluationAnalyticsOut)
def get_analytics_evaluation(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    search_backend: SearchBackend = Query(default=SearchBackend.POSTGRESQL),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EvaluationAnalyticsOut:
    resolved_from, resolved_to = _resolve_range(date_from, date_to)
    return evaluation_service.get_evaluation_analytics(db, search_backend, resolved_from, resolved_to)


@router.get("/evaluation/test-cases", response_model=list[EvaluationTestCaseOut])
def list_evaluation_test_cases(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> list[EvaluationTestCase]:
    return db.query(EvaluationTestCase).order_by(EvaluationTestCase.id.asc()).all()


@router.post(
    "/evaluation/test-cases", response_model=EvaluationTestCaseOut, status_code=status.HTTP_201_CREATED
)
def create_evaluation_test_case(
    payload: EvaluationTestCaseCreate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> EvaluationTestCase:
    video = db.query(Video).filter(Video.id == payload.expected_video_id).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="expected_video_id does not match any upload."
        )

    test_case = EvaluationTestCase(
        created_by_admin_id=current_admin.id,
        test_name=payload.test_name,
        query_text=payload.query_text,
        search_type=payload.search_type,
        search_scope=payload.search_scope,
        expected_video_id=payload.expected_video_id,
        expected_start_time=payload.expected_start_time,
        expected_end_time=payload.expected_end_time,
        timestamp_tolerance_seconds=payload.timestamp_tolerance_seconds,
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    return test_case


@router.post("/evaluation/run", response_model=RunEvaluationResponse)
def run_evaluation(
    payload: RunEvaluationRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> RunEvaluationResponse:
    try:
        results = evaluation_service.run_test_cases(
            db, current_admin, payload.search_backend, payload.test_case_id, payload.result_limit
        )
    except evaluation_service.ElasticsearchUnavailableError as exc:
        # Expected degraded state (ES unavailable), not logged as an error.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.reason)
    except Exception as exc:
        # Unexpected failure: log it, then re-raise so FastAPI's default handler
        # still returns 500.
        error_log_service.log_error(
            db, error_source="evaluation_run", error_message=str(exc), user_id=current_admin.id
        )
        raise
    return RunEvaluationResponse(search_backend=payload.search_backend, ran_count=len(results), results=results)


@router.get("/elasticsearch/health")
def get_elasticsearch_health(current_admin: User = Depends(get_current_admin)) -> dict:
    available = elasticsearch_service.is_available()
    return {"available": available}


@router.post("/elasticsearch/backfill", status_code=status.HTTP_200_OK)
def run_elasticsearch_backfill(
    current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> dict:
    try:
        count = elasticsearch_service.backfill(db)
    except elasticsearch_service.ElasticsearchUnavailableError as exc:
        # Expected degraded state, not logged as an error.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.reason)
    except Exception as exc:
        error_log_service.log_error(
            db, error_source="elasticsearch_backfill", error_message=str(exc), user_id=current_admin.id
        )
        raise
    return {"indexed_count": count}


# Exports only aggregate values already shown in the UI; no raw per-user data.
@router.get("/analytics/export")
def export_analytics_csv(
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
    search_backend: SearchBackend = Query(default=SearchBackend.POSTGRESQL),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    resolved_from, resolved_to = _resolve_range(date_from, date_to)
    overview = analytics_service.get_operational_analytics(db, resolved_from, resolved_to, None)
    evaluation = evaluation_service.get_evaluation_analytics(db, search_backend, resolved_from, resolved_to)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ReCall Analytics & Evaluation Export"])
    writer.writerow(["Date range", f"{resolved_from} to {resolved_to}"])
    writer.writerow(["Evaluation backend", search_backend.value])
    writer.writerow([])
    writer.writerow(["Operational metric", "Value", "Previous period", "Delta %"])
    writer.writerow(["Average Response Time (ms)", overview.average_response_time_ms.value, overview.average_response_time_ms.previous_value, overview.average_response_time_ms.delta_percent])
    writer.writerow(["Media Files Indexed", overview.media_files_indexed.value, overview.media_files_indexed.previous_value, overview.media_files_indexed.delta_percent])
    writer.writerow(["Queries Processed", overview.queries_processed.value, overview.queries_processed.previous_value, overview.queries_processed.delta_percent])
    writer.writerow([])
    writer.writerow(["Query distribution", "Count", "Percent"])
    for entry in overview.query_distribution:
        writer.writerow([entry.search_type.value, entry.count, entry.percent])
    writer.writerow([])
    writer.writerow(["Pipeline health", "Value"])
    writer.writerow(["Media Processed", overview.pipeline_health.media_processed])
    writer.writerow(["Transcript Segments Generated", overview.pipeline_health.transcript_segments_generated])
    writer.writerow(["Clips Created", overview.pipeline_health.clips_created])
    writer.writerow(["Failed Uploads", overview.pipeline_health.failed_uploads])
    writer.writerow([])
    if not evaluation.backend_available:
        writer.writerow(["Evaluation", evaluation.unavailable_reason or "Unavailable"])
    elif not evaluation.method_rows:
        writer.writerow(["Evaluation", evaluation.unavailable_reason or "No evaluation results for this period."])
    else:
        writer.writerow(["Search Method", "Accuracy", "Precision", "Recall", "F1", "Sample Count"])
        for row in evaluation.method_rows:
            writer.writerow([row.search_type.value, row.accuracy, row.precision, row.recall, row.f1, row.sample_count])

    buffer.seek(0)
    filename = f"recall_analytics_{resolved_from}_{resolved_to}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
