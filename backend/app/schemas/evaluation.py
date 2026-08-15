from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import SearchBackend, SearchScope, SearchType
from app.models.evaluation_test_case import DEFAULT_TIMESTAMP_TOLERANCE_SECONDS


# Only these are currently runnable -- run_test_cases skips any row with query_text=None, and there's no audio-test-case runner yet.
CREATABLE_SEARCH_TYPES = (SearchType.EXACT_TEXT, SearchType.SEMANTIC)


class EvaluationTestCaseCreate(BaseModel):
    test_name: str
    query_text: str
    search_type: SearchType
    search_scope: SearchScope = SearchScope.BOTH
    expected_video_id: int
    expected_start_time: float
    expected_end_time: float
    timestamp_tolerance_seconds: float = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS

    @field_validator("test_name", "query_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("search_type")
    @classmethod
    def _runnable_search_type(cls, value: SearchType) -> SearchType:
        if value not in CREATABLE_SEARCH_TYPES:
            raise ValueError(
                f"search_type must be one of {[t.value for t in CREATABLE_SEARCH_TYPES]} "
                "-- evaluation_service.run_test_cases only supports query_text-driven test "
                "cases today (see its own docstring)."
            )
        return value

    @model_validator(mode="after")
    def _valid_window(self) -> "EvaluationTestCaseCreate":
        if self.expected_start_time < 0:
            raise ValueError("expected_start_time must not be negative")
        if self.expected_end_time <= self.expected_start_time:
            raise ValueError("expected_end_time must be greater than expected_start_time")
        if self.timestamp_tolerance_seconds < 0:
            raise ValueError("timestamp_tolerance_seconds must not be negative")
        return self


class EvaluationTestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_name: str
    query_text: str | None
    search_type: SearchType
    search_scope: SearchScope
    expected_video_id: int
    expected_start_time: float
    expected_end_time: float
    timestamp_tolerance_seconds: float
    created_at: datetime.datetime


class RunEvaluationRequest(BaseModel):
    search_backend: SearchBackend = SearchBackend.POSTGRESQL
    # None runs every test case; a specific id runs just that one.
    test_case_id: int | None = None
    result_limit: int = 20


class EvaluationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_case_id: int
    search_backend: SearchBackend
    is_correct: bool
    accuracy_score: float | None
    precision_at_k: float | None
    recall_at_k: float | None
    reciprocal_rank: float | None
    response_time_ms: float | None
    evaluated_at: datetime.datetime


class RunEvaluationResponse(BaseModel):
    search_backend: SearchBackend
    ran_count: int
    results: list[EvaluationResultOut]
