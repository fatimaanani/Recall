"""
test_search_error_logging.py

Dedicated unit tests for app/services/error_log_service.py -- the
centralized `error_logs` writer. Call-site coverage for the modules that
invoke log_error() lives in their own existing test files (referenced
below); this file tests error_log_service.log_error() itself in
isolation.

1. Shared helpers
2. log_error persists the expected row
3. Defensive rollback-before-write (PendingRollbackError avoidance)
4. Message sanitization (storage-root stripping, truncation)
5. Swallow-on-failure contract (never raises, never masks the caller's
   own exception)

Call-site assertions (log_error is actually invoked, without changing
existing API/exception behavior) live in:
  - test_search_service.py (exact text / semantic search retrieval failures)
  - test_speech_to_text_search.py (speech-query transcription + retrieval
    failures)
  - test_clip_service.py (match_resolver + clip-generation failures)
admin_analytics.py's evaluation-run / Elasticsearch-backfill logging
wraps genuinely unexpected exceptions only (the expected
ElasticsearchUnavailableError honest-degradation path is deliberately
NOT logged, same as elsewhere in this codebase) and is not separately
unit-tested here -- it reuses the exact log_error() contract already
covered here, wired the same way as the other call sites.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import error_log_service


# ===========================================================================
# 1. Shared helpers
# ===========================================================================

def _make_settings(storage_root: str = "/srv/recall/storage") -> SimpleNamespace:
    return SimpleNamespace(storage_root=storage_root)


def _make_mock_db():
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append
    mock_db.commit.side_effect = lambda: None
    mock_db.rollback.side_effect = lambda: None
    mock_db._added = added
    return mock_db


# ===========================================================================
# 2. log_error persists the expected row
# ===========================================================================

def test_log_error_persists_a_single_error_log_with_given_fields(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()

    error_log_service.log_error(
        db,
        error_source="exact_text_search",
        error_message="something went wrong",
        user_id=7,
        search_query_id=3,
        search_result_id=None,
        video_id=None,
    )

    assert len(db._added) == 1
    entry = db._added[0]
    assert entry.error_source == "exact_text_search"
    assert entry.error_message == "something went wrong"
    assert entry.user_id == 7
    assert entry.search_query_id == 3
    assert entry.search_result_id is None
    assert entry.video_id is None
    db.commit.assert_called_once()


def test_log_error_defaults_every_optional_fk_to_none(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()

    error_log_service.log_error(db, error_source="clip_generation", error_message="ffmpeg failed")

    entry = db._added[0]
    assert entry.user_id is None
    assert entry.search_query_id is None
    assert entry.search_result_id is None
    assert entry.video_id is None


# ===========================================================================
# 3. Defensive rollback-before-write
# ===========================================================================

def test_log_error_rolls_back_before_adding_the_row(mocker):
    # The primary real-world caller is inside an `except SQLAlchemyError`
    # block, where the session may already be in SQLAlchemy's "pending
    # rollback" state -- log_error must clear that state before it does
    # anything else, or its own db.add()/db.commit() would raise
    # PendingRollbackError and the log would never actually be written.
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()
    call_order: list[str] = []
    db.rollback.side_effect = lambda: call_order.append("rollback")
    db.add.side_effect = lambda obj: call_order.append("add") or db._added.append(obj)
    db.commit.side_effect = lambda: call_order.append("commit")

    error_log_service.log_error(db, error_source="semantic_search", error_message="boom")

    assert call_order == ["rollback", "add", "commit"]


# ===========================================================================
# 4. Message sanitization
# ===========================================================================

def test_log_error_strips_storage_root_prefix_from_message(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings("/srv/recall/storage"))
    db = _make_mock_db()

    error_log_service.log_error(
        db,
        error_source="media_processing",
        error_message="file not found: /srv/recall/storage/videos/42/source.mp4",
    )

    entry = db._added[0]
    assert "/srv/recall/storage" not in entry.error_message
    assert entry.error_message == "file not found: <storage>/videos/42/source.mp4"


def test_log_error_truncates_overly_long_messages(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()

    error_log_service.log_error(db, error_source="elasticsearch_sync", error_message="x" * 5000)

    entry = db._added[0]
    assert len(entry.error_message) == error_log_service._MAX_MESSAGE_LENGTH


def test_log_error_handles_empty_storage_root_without_erroring(mocker):
    # settings.storage_root could be falsy in a misconfigured environment --
    # sanitization must not crash on it, just skip the substring replace.
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings(storage_root=""))
    db = _make_mock_db()

    error_log_service.log_error(db, error_source="clip_generation", error_message="plain message")

    assert db._added[0].error_message == "plain message"


# ===========================================================================
# 5. Swallow-on-failure contract
# ===========================================================================

def test_log_error_never_raises_when_commit_fails(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()
    db.commit.side_effect = Exception("db is down")

    # Must not raise -- a logging failure must never mask or replace
    # whatever exception the caller was already handling.
    error_log_service.log_error(db, error_source="exact_text_search", error_message="original failure")

    db.rollback.assert_called()


def test_log_error_never_raises_when_rollback_itself_fails(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()
    db.rollback.side_effect = Exception("rollback unavailable")

    error_log_service.log_error(db, error_source="clip_generation", error_message="original failure")
    # No assertion beyond "did not raise" -- there is nothing left this
    # function can safely do once even rollback fails.


def test_log_error_never_raises_when_add_fails(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()
    db.add.side_effect = Exception("unexpected ORM error")

    error_log_service.log_error(db, error_source="semantic_search", error_message="original failure")


def test_log_error_logs_its_own_failure_via_the_module_logger(mocker):
    mocker.patch.object(error_log_service, "get_settings", return_value=_make_settings())
    db = _make_mock_db()
    db.commit.side_effect = Exception("db is down")
    logger_mock = mocker.patch.object(error_log_service, "logger")

    error_log_service.log_error(db, error_source="clip_generation", error_message="original failure")

    logger_mock.exception.assert_called_once()
