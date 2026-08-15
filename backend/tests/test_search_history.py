"""
test_search_history.py

1. Shared helpers
2. Unit tests -- ownership predicate (compiled-SQL assertions, no DB, no admin bypass)
3. Unit tests -- list_search_history orchestration (mocked DB)
4. Unit tests -- SearchHistoryEntryOut mapping per query_type
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest

from app.enums import SearchScope, SearchType, UserRole
from app.models.search_query import SearchQuery
from app.models.user import User
from app.schemas.search import SearchHistoryEntryOut
from app.services import search_history_service


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


def _make_query(**overrides) -> SearchQuery:
    defaults = dict(
        id=1,
        user_id=1,
        query_text="hello world",
        original_audio_filename=None,
        transcribed_text=None,
        query_type=SearchType.EXACT_TEXT,
        search_scope=SearchScope.BOTH,
        results_found=3,
        response_time_ms=120.5,
        created_at=dt.datetime(2026, 8, 1, 10, 0, 0),
    )
    defaults.update(overrides)
    return SearchQuery(**defaults)


# Mock DB whose query(...).filter(...).order_by(...).limit(...).all() chain
# returns a fixed list of entries -- same MagicMock-chain style as
# test_search_service.py's mocked-DB tests, since list_search_history has
# no branching logic worth a fuller fake session.
def _make_mock_db(entries):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = entries
    return mock_db


# ===========================================================================
# 2. Unit tests -- ownership predicate (compiled-SQL assertions, no DB, no admin bypass)
# ===========================================================================

def test_owner_predicate_filters_by_user_id_only():
    user = _make_user(id=7)
    compiled = str(search_history_service._owner_predicate(user))
    assert "search_queries.user_id" in compiled


def test_owner_predicate_has_no_role_branch_even_for_admin_user():
    # Structural proof of "no admin bypass": the predicate for an admin
    # user is exactly the same shape as for a regular user -- there is no
    # role check to get wrong or forget, unlike search_service's
    # MY_LIBRARY/SHARED_LIBRARY/BOTH scope predicate which does branch.
    admin = _make_user(id=7, role=UserRole.ADMIN)
    compiled = str(search_history_service._owner_predicate(admin))
    assert "search_queries.user_id" in compiled
    assert "role" not in compiled.lower()
    assert " OR " not in compiled  # single condition, not a branch


# ===========================================================================
# 3. Unit tests -- list_search_history orchestration (mocked DB)
# ===========================================================================

def test_list_search_history_filters_by_current_user_only():
    user = _make_user(id=42)
    mock_db = _make_mock_db([])

    search_history_service.list_search_history(mock_db, user, limit=10)

    filter_call = mock_db.query.return_value.filter
    filter_call.assert_called_once()
    predicate = filter_call.call_args[0][0]
    assert "search_queries.user_id" in str(predicate)


def test_list_search_history_orders_newest_first():
    user = _make_user(id=3)
    mock_db = _make_mock_db([])

    search_history_service.list_search_history(mock_db, user, limit=10)

    order_by_call = mock_db.query.return_value.filter.return_value.order_by
    order_by_call.assert_called_once()
    compiled = str(order_by_call.call_args[0][0])
    assert "search_queries.created_at" in compiled
    assert "DESC" in compiled


def test_list_search_history_passes_limit_through_to_query():
    user = _make_user(id=3)
    mock_db = _make_mock_db([])

    search_history_service.list_search_history(mock_db, user, limit=7)

    limit_call = mock_db.query.return_value.filter.return_value.order_by.return_value.limit
    limit_call.assert_called_once_with(7)


def test_list_search_history_empty_history_returns_empty_list():
    user = _make_user(id=3)
    mock_db = _make_mock_db([])

    result = search_history_service.list_search_history(mock_db, user, limit=10)

    assert result == []


def test_list_search_history_returns_entries_from_query_unmodified():
    user = _make_user(id=3)
    entries = [_make_query(id=1), _make_query(id=2)]
    mock_db = _make_mock_db(entries)

    result = search_history_service.list_search_history(mock_db, user, limit=10)

    assert result == entries


def test_list_search_history_rejects_limit_below_one():
    user = _make_user(id=3)
    mock_db = MagicMock()

    with pytest.raises(search_history_service.InvalidHistoryLimitError):
        search_history_service.list_search_history(mock_db, user, limit=0)
    mock_db.query.assert_not_called()


def test_list_search_history_rejects_limit_above_one_hundred():
    user = _make_user(id=3)
    mock_db = MagicMock()

    with pytest.raises(search_history_service.InvalidHistoryLimitError):
        search_history_service.list_search_history(mock_db, user, limit=101)
    mock_db.query.assert_not_called()


# ===========================================================================
# 4. Unit tests -- SearchHistoryEntryOut mapping per query_type
# ===========================================================================

def test_search_history_entry_out_maps_exact_text_query():
    query = _make_query(
        query_type=SearchType.EXACT_TEXT,
        query_text="I'll protect you",
        transcribed_text=None,
        original_audio_filename=None,
    )
    entry = SearchHistoryEntryOut.model_validate(query)

    assert entry.query_type == SearchType.EXACT_TEXT
    assert entry.query_text == "I'll protect you"
    assert entry.transcribed_text is None
    assert entry.original_audio_filename is None


def test_search_history_entry_out_maps_semantic_query():
    query = _make_query(
        id=2,
        query_type=SearchType.SEMANTIC,
        query_text="a car chase through the city",
        transcribed_text=None,
        original_audio_filename=None,
    )
    entry = SearchHistoryEntryOut.model_validate(query)

    assert entry.query_type == SearchType.SEMANTIC
    assert entry.query_text == "a car chase through the city"
    assert entry.transcribed_text is None
    assert entry.original_audio_filename is None


def test_search_history_entry_out_maps_speech_to_text_query():
    query = _make_query(
        id=3,
        query_type=SearchType.SPEECH_TO_TEXT,
        query_text=None,
        transcribed_text="I'll protect you",
        original_audio_filename="uploaded_voice_01.wav",
    )
    entry = SearchHistoryEntryOut.model_validate(query)

    assert entry.query_type == SearchType.SPEECH_TO_TEXT
    assert entry.query_text is None
    assert entry.transcribed_text == "I'll protect you"
    assert entry.original_audio_filename == "uploaded_voice_01.wav"


def test_search_history_entry_out_maps_meta_fields():
    query = _make_query(
        results_found=5,
        response_time_ms=87.25,
        created_at=dt.datetime(2026, 7, 30, 9, 15, 0),
    )
    entry = SearchHistoryEntryOut.model_validate(query)

    assert entry.results_found == 5
    assert entry.response_time_ms == 87.25
    assert entry.created_at == dt.datetime(2026, 7, 30, 9, 15, 0)
