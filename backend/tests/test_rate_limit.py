"""
test_rate_limit.py

Unit tests for app/utils/rate_limit.py -- the small in-memory
sliding-window limiter backing the high-risk-endpoint limits (login,
registration, search, speech search, upload). Exercises the dependency
callables directly (fake Request / fake user objects, no FastAPI
TestClient, no database) -- consistent with how every other
service/dependency module in this codebase is unit-tested, and avoids
needing a real Postgres database just to prove a counter works.

Router wiring itself (auth.py/search.py/videos.py each declaring
`_rate_limit: None = Depends(...)`) is verified by py_compile plus visual
inspection -- a genuine end-to-end 429 over HTTP would need TestClient +
pg_session (see test_admin_analytics_api.py's precedent), which is
deliberately not duplicated here for five routes whose only new behavior
is "call this already-tested dependency".

1. Shared helpers
2. _is_allowed sliding-window behavior (the core algorithm)
3. rate_limit_by_ip dependency
4. rate_limit_by_user dependency
5. reset_rate_limits() test-isolation helper
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.utils import rate_limit


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _fake_request(host: str = "203.0.113.5") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


def _fake_user(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


# ===========================================================================
# 2. _is_allowed sliding-window behavior
# ===========================================================================

def test_is_allowed_permits_up_to_max_requests_within_window():
    key = "unit_bucket_a"
    for _ in range(5):
        assert rate_limit._is_allowed(key, max_requests=5, window_seconds=60.0) is True


def test_is_allowed_rejects_the_request_over_the_limit():
    key = "unit_bucket_b"
    for _ in range(3):
        assert rate_limit._is_allowed(key, max_requests=3, window_seconds=60.0) is True
    assert rate_limit._is_allowed(key, max_requests=3, window_seconds=60.0) is False


def test_is_allowed_expires_old_timestamps_out_of_the_window(mocker):
    key = "unit_bucket_c"
    clock = {"now": 1000.0}
    mocker.patch.object(rate_limit.time, "monotonic", side_effect=lambda: clock["now"])

    for _ in range(2):
        assert rate_limit._is_allowed(key, max_requests=2, window_seconds=10.0) is True
    assert rate_limit._is_allowed(key, max_requests=2, window_seconds=10.0) is False

    # Advance past the window -- the two old timestamps must be pruned,
    # freeing up capacity again instead of the bucket staying full forever.
    clock["now"] += 11.0
    assert rate_limit._is_allowed(key, max_requests=2, window_seconds=10.0) is True


def test_is_allowed_keys_are_independent_of_each_other():
    assert rate_limit._is_allowed("bucket_x", max_requests=1, window_seconds=60.0) is True
    assert rate_limit._is_allowed("bucket_x", max_requests=1, window_seconds=60.0) is False
    # A different key must not be affected by bucket_x's exhausted limit.
    assert rate_limit._is_allowed("bucket_y", max_requests=1, window_seconds=60.0) is True


# ===========================================================================
# 3. rate_limit_by_ip dependency
# ===========================================================================

def test_rate_limit_by_ip_allows_requests_under_the_limit():
    dependency = rate_limit.rate_limit_by_ip("test_ip_bucket", max_requests=2, window_seconds=60.0)
    dependency(_fake_request())
    dependency(_fake_request())  # must not raise


def test_rate_limit_by_ip_raises_429_over_the_limit():
    dependency = rate_limit.rate_limit_by_ip("test_ip_bucket_2", max_requests=1, window_seconds=60.0)
    dependency(_fake_request())

    with pytest.raises(HTTPException) as exc_info:
        dependency(_fake_request())
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_by_ip_tracks_each_ip_independently():
    dependency = rate_limit.rate_limit_by_ip("test_ip_bucket_3", max_requests=1, window_seconds=60.0)
    dependency(_fake_request(host="10.0.0.1"))
    # A second, different IP must have its own untouched allowance.
    dependency(_fake_request(host="10.0.0.2"))


def test_rate_limit_by_ip_falls_back_to_unknown_when_client_is_none():
    dependency = rate_limit.rate_limit_by_ip("test_ip_bucket_4", max_requests=1, window_seconds=60.0)
    request_without_client = SimpleNamespace(client=None)
    dependency(request_without_client)  # must not raise (AttributeError etc.)


# ===========================================================================
# 4. rate_limit_by_user dependency
# ===========================================================================

def test_rate_limit_by_user_allows_requests_under_the_limit():
    dependency = rate_limit.rate_limit_by_user("test_user_bucket", max_requests=2, window_seconds=60.0)
    dependency(current_user=_fake_user(1))
    dependency(current_user=_fake_user(1))  # must not raise


def test_rate_limit_by_user_raises_429_over_the_limit():
    dependency = rate_limit.rate_limit_by_user("test_user_bucket_2", max_requests=1, window_seconds=60.0)
    dependency(current_user=_fake_user(1))

    with pytest.raises(HTTPException) as exc_info:
        dependency(current_user=_fake_user(1))
    assert exc_info.value.status_code == 429


def test_rate_limit_by_user_tracks_each_user_independently():
    dependency = rate_limit.rate_limit_by_user("test_user_bucket_3", max_requests=1, window_seconds=60.0)
    dependency(current_user=_fake_user(1))
    # A different user id must have its own untouched allowance -- this is
    # exactly why search/upload use user-keyed limiting, not IP-keyed (a
    # shared/NAT'd IP must not make two different accounts rate-limit
    # each other).
    dependency(current_user=_fake_user(2))


def test_two_buckets_for_the_same_user_do_not_share_a_limit():
    # search_text and search_speech are separate buckets even for the same
    # user/route-group -- exhausting one must not affect the other.
    text_dependency = rate_limit.rate_limit_by_user("search_text", max_requests=1, window_seconds=60.0)
    speech_dependency = rate_limit.rate_limit_by_user("search_speech", max_requests=1, window_seconds=60.0)

    text_dependency(current_user=_fake_user(9))
    speech_dependency(current_user=_fake_user(9))  # must not raise


# ===========================================================================
# 5. reset_rate_limits() test-isolation helper
# ===========================================================================

def test_reset_rate_limits_clears_all_buckets():
    dependency = rate_limit.rate_limit_by_ip("test_reset_bucket", max_requests=1, window_seconds=60.0)
    dependency(_fake_request())
    with pytest.raises(HTTPException):
        dependency(_fake_request())

    rate_limit.reset_rate_limits()

    dependency(_fake_request())  # allowed again -- the bucket was cleared
