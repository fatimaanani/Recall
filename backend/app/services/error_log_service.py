"""Centralized, best-effort writer for the `error_logs` table. log_error() never raises: it rolls back first, since callers invoke it from inside an except block where the session may be in a pending-rollback state, and it swallows its own failures so a logging problem can never mask the caller's real exception. error_message is sanitized to strip the storage-root path prefix and truncated to a bounded length."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.error_log import ErrorLog

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 2000


def _sanitize_message(message: str) -> str:
    text = str(message or "")
    settings = get_settings()
    if settings.storage_root:
        text = text.replace(settings.storage_root, "<storage>")
    return text[:_MAX_MESSAGE_LENGTH]


def log_error(
    db: Session,
    *,
    error_source: str,
    error_message: str,
    user_id: int | None = None,
    search_query_id: int | None = None,
    search_result_id: int | None = None,
    video_id: int | None = None,
) -> None:
    """Best-effort write; never raises, so a logging failure can't mask the caller's real exception."""
    try:
        db.rollback()  # clear any pending-rollback state left by the caller's own failed operation
        entry = ErrorLog(
            user_id=user_id,
            search_query_id=search_query_id,
            search_result_id=search_result_id,
            video_id=video_id,
            error_source=error_source,
            error_message=_sanitize_message(error_message),
        )
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001 -- logging must never raise or replace the caller's own exception
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            logger.exception("Failed to write error_logs row for source=%s", error_source)
        except Exception:  # noqa: BLE001
            pass
