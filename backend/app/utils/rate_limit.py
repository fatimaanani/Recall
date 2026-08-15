"""
Small in-memory sliding-window rate limiter for the high-risk endpoints:
login, registration, search, upload, and password reset.

Not a third-party dependency (no slowapi/limits) to keep this project's
dependencies minimal. A sliding window, rather than a fixed window or
token bucket, avoids letting 2x max_requests through at a window boundary.

State lives in one process's memory, so it resets on restart and isn't
shared across multiple worker processes -- an accepted tradeoff for a
single-instance deployment.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.models.user import User

_buckets: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _is_allowed(key: str, max_requests: int, window_seconds: float) -> bool:
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        timestamps = _buckets[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return False
        timestamps.append(now)
        return True


def _too_many_requests(window_seconds: float) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please try again later.",
        headers={"Retry-After": str(int(window_seconds))},
    )


def reset_rate_limits() -> None:
    """Test-only helper -- clears all in-memory buckets so one test's
    requests don't count against the next test's limit."""
    with _lock:
        _buckets.clear()


def rate_limit_by_ip(bucket: str, max_requests: int, window_seconds: float):
    def _dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        if not _is_allowed(f"{bucket}:{client_host}", max_requests, window_seconds):
            raise _too_many_requests(window_seconds)

    return _dependency


def rate_limit_by_user(bucket: str, max_requests: int, window_seconds: float):
    def _dependency(current_user: User = Depends(get_current_user)) -> None:
        if not _is_allowed(f"{bucket}:{current_user.id}", max_requests, window_seconds):
            raise _too_many_requests(window_seconds)

    return _dependency
