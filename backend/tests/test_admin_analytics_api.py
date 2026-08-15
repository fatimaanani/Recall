"""
test_admin_analytics_api.py

Router-level tests for app/api/admin_analytics.py, using FastAPI's
TestClient + dependency_overrides -- the first TestClient-based tests in
this codebase (every other test file exercises the service layer
directly). Needed here specifically because "admin auth / non-admin
rejection" is a router-boundary concern (get_current_admin is a FastAPI
dependency), not something analytics_service.py or evaluation_service.py
can be asked about directly.

Two dependencies are overridden, never three: get_db (-> the real
pg_session fixture, so these hit a real, isolated, rolled-back-after-test
database exactly like every other integration test here) and
get_current_user (-> a plain in-memory User, admin or not -- never a real
JWT). get_current_admin itself is never overridden: for the "non-admin
rejection" tests, the real get_current_admin logic must run and reject,
otherwise the test would prove nothing.

TestClient is instantiated WITHOUT the `with` context-manager form, so
app.main's lifespan (startup DB recovery + embedding backfill) never
runs -- that lifespan code calls SessionLocal() directly against
settings.database_url, bypassing get_db entirely, and would try to reach
a real database this test run has no reason to depend on.

1. Shared fixtures (client, admin user, non-admin user)
2. Non-admin rejection -- every admin-only route
3. Admin success -- honest response shapes
4. No private data leakage in the raw JSON response
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.enums import MediaSourceType, MediaStatus, MediaVisibility, UserRole
from app.main import app
from app.models.user import User
from app.models.video import Video

# ===========================================================================
# 1. Shared fixtures
# ===========================================================================


@pytest.fixture
def admin_user() -> User:
    return User(id=1, full_name="Admin", username="admintest", email="admintest@example.com", password_hash="x", role=UserRole.ADMIN)


@pytest.fixture
def regular_user() -> User:
    return User(id=2, full_name="Regular", username="regulartest", email="regulartest@example.com", password_hash="x", role=UserRole.USER)


@pytest.fixture
def client(pg_session):
    def _override_get_db():
        yield pg_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _as(client, user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


ADMIN_ONLY_GET_ROUTES = [
    "/api/admin/analytics/overview",
    "/api/admin/analytics/evaluation",
    "/api/admin/evaluation/test-cases",
    "/api/admin/elasticsearch/health",
    "/api/admin/analytics/export",
]


# ===========================================================================
# 2. Non-admin rejection
# ===========================================================================


@pytest.mark.parametrize("route", ADMIN_ONLY_GET_ROUTES)
def test_non_admin_user_is_rejected_with_403(client, regular_user, route):
    response = _as(client, regular_user).get(route)
    assert response.status_code == 403


def test_non_admin_user_is_rejected_from_run_evaluation(client, regular_user):
    response = _as(client, regular_user).post("/api/admin/evaluation/run", json={"search_backend": "postgresql"})
    assert response.status_code == 403


def test_non_admin_user_is_rejected_from_elasticsearch_backfill(client, regular_user):
    response = _as(client, regular_user).post("/api/admin/elasticsearch/backfill")
    assert response.status_code == 403


def test_non_admin_user_is_rejected_from_creating_a_test_case(client, regular_user):
    response = _as(client, regular_user).post(
        "/api/admin/evaluation/test-cases",
        json={
            "test_name": "t", "query_text": "q", "search_type": "exact_text",
            "expected_video_id": 1, "expected_start_time": 0, "expected_end_time": 5,
        },
    )
    assert response.status_code == 403


def test_unauthenticated_request_is_rejected_not_admin_bypassed(client):
    # No dependency override at all for get_current_user here -- the real
    # get_current_user must run and reject a request with no credentials.
    response = client.get("/api/admin/analytics/overview")
    assert response.status_code == 401


# ===========================================================================
# 3. Admin success -- honest response shapes
# ===========================================================================


def test_admin_can_load_analytics_overview(client, admin_user):
    response = _as(client, admin_user).get("/api/admin/analytics/overview")
    assert response.status_code == 200
    body = response.json()
    assert "queries_processed" in body
    assert "response_time_series" in body
    assert "query_distribution" in body
    assert "pipeline_health" in body
    # search_accuracy is intentionally always None on this endpoint -- the
    # real, toggle-aware number lives on /analytics/evaluation only.
    assert body["search_accuracy"] is None


def test_admin_can_load_analytics_evaluation_for_postgresql(client, admin_user):
    response = _as(client, admin_user).get("/api/admin/analytics/evaluation", params={"search_backend": "postgresql"})
    assert response.status_code == 200
    body = response.json()
    assert body["search_backend"] == "postgresql"
    assert body["backend_available"] is True


def test_admin_gets_honest_unavailable_state_for_elasticsearch_when_disabled(client, admin_user):
    response = _as(client, admin_user).get("/api/admin/analytics/evaluation", params={"search_backend": "elasticsearch"})
    assert response.status_code == 200
    body = response.json()
    assert body["backend_available"] is False
    assert body["unavailable_reason"] == "Elasticsearch evaluation is not configured yet."
    assert body["method_rows"] == []


def test_admin_gets_422_for_an_invalid_date_range(client, admin_user):
    response = _as(client, admin_user).get(
        "/api/admin/analytics/overview",
        params={"date_from": "2026-06-20", "date_to": "2026-06-01"},
    )
    assert response.status_code == 422


def test_elasticsearch_health_reports_unavailable_without_crashing(client, admin_user):
    response = _as(client, admin_user).get("/api/admin/elasticsearch/health")
    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_elasticsearch_backfill_returns_503_not_a_500_when_unavailable(client, admin_user):
    response = _as(client, admin_user).post("/api/admin/elasticsearch/backfill")
    assert response.status_code == 503


# ===========================================================================
# 4. No private data leakage
# ===========================================================================


def _pg_make_admin(pg_session, **overrides) -> User:
    defaults = dict(
        full_name="Persisted Admin", username=f"pgadmin{id(overrides)}",
        email=f"pgadmin{id(overrides)}@example.com", password_hash="x", role=UserRole.ADMIN,
    )
    defaults.update(overrides)
    admin = User(**defaults)
    pg_session.add(admin)
    pg_session.flush()
    return admin


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


# ===========================================================================
# 5. Evaluation test case creation (2026-08-14 -- this table had no writer
#    anywhere in the app before this; see EvaluationTestCaseCreate's own
#    docstring for the search_type restriction reasoning)
# ===========================================================================


def test_admin_can_create_an_evaluation_test_case(client, pg_session):
    admin = _pg_make_admin(pg_session)
    video = _pg_make_video(pg_session, admin.id)

    response = _as(client, admin).post(
        "/api/admin/evaluation/test-cases",
        json={
            "test_name": "Recursion lecture lookup",
            "query_text": "recursion example",
            "search_type": "semantic",
            "search_scope": "both",
            "expected_video_id": video.id,
            "expected_start_time": 10.0,
            "expected_end_time": 20.0,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["test_name"] == "Recursion lecture lookup"
    assert body["expected_video_id"] == video.id
    # Default tolerance applied when omitted from the request
    assert body["timestamp_tolerance_seconds"] == 5.0

    listed = _as(client, admin).get("/api/admin/evaluation/test-cases")
    assert any(row["id"] == body["id"] for row in listed.json())


def test_create_test_case_404s_for_an_unknown_video(client, pg_session):
    admin = _pg_make_admin(pg_session)

    response = _as(client, admin).post(
        "/api/admin/evaluation/test-cases",
        json={
            "test_name": "t", "query_text": "q", "search_type": "exact_text",
            "expected_video_id": 999999, "expected_start_time": 0, "expected_end_time": 5,
        },
    )
    assert response.status_code == 404


def test_create_test_case_rejects_speech_to_text_as_unrunnable(client, pg_session):
    # run_test_cases only supports query_text-driven test cases -- see
    # EvaluationTestCaseCreate's _runnable_search_type validator.
    admin = _pg_make_admin(pg_session)
    video = _pg_make_video(pg_session, admin.id)

    response = _as(client, admin).post(
        "/api/admin/evaluation/test-cases",
        json={
            "test_name": "t", "query_text": "q", "search_type": "speech_to_text",
            "expected_video_id": video.id, "expected_start_time": 0, "expected_end_time": 5,
        },
    )
    assert response.status_code == 422


def test_create_test_case_rejects_end_time_before_start_time(client, pg_session):
    admin = _pg_make_admin(pg_session)
    video = _pg_make_video(pg_session, admin.id)

    response = _as(client, admin).post(
        "/api/admin/evaluation/test-cases",
        json={
            "test_name": "t", "query_text": "q", "search_type": "exact_text",
            "expected_video_id": video.id, "expected_start_time": 20.0, "expected_end_time": 5.0,
        },
    )
    assert response.status_code == 422


def test_analytics_overview_response_never_contains_raw_query_text(client, admin_user, pg_session):
    from app.enums import SearchScope, SearchType
    from app.models.search_query import SearchQuery

    user = User(full_name="Leak Test", username="leaktestuser", email="leaktest@example.com", password_hash="x")
    pg_session.add(user)
    pg_session.flush()
    query = SearchQuery(
        user_id=user.id, query_text="a very specific private search phrase",
        query_type=SearchType.EXACT_TEXT, search_scope=SearchScope.BOTH,
    )
    pg_session.add(query)
    pg_session.commit()

    response = _as(client, admin_user).get("/api/admin/analytics/overview")
    assert "a very specific private search phrase" not in response.text
