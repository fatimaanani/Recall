"""
test_password_reset_service.py

Unit tests for app/services/password_reset_service.py (user-self-service
forgot-password flow). Mocked DB session -- no Postgres needed,
consistent with test_search_error_logging.py's convention for a service
this size.

1. Shared helpers
2. request_password_reset -- no email enumeration
3. request_password_reset -- token creation for a real account
4. reset_password -- success
5. reset_password -- invalid/expired/used token rejection
6. Token hashing
"""

from __future__ import annotations

import datetime
import hashlib
from unittest.mock import MagicMock

from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services import password_reset_service


def _make_user(**overrides) -> User:
    defaults = dict(
        id=1, full_name="Test User", username="testuser", email="test@example.com",
        password_hash="old-hash",
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_mock_db(user=None, token_row=None, token_row_user=None):
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append
    mock_db.commit.side_effect = lambda: None
    mock_db._added = added

    def _query(model):
        q = MagicMock()
        q.filter.return_value = q
        if model is User:
            q.first.return_value = token_row_user if token_row_user is not None else user
        elif model is PasswordResetToken:
            q.first.return_value = token_row
        else:
            q.first.return_value = None
        return q

    mock_db.query.side_effect = _query
    return mock_db


# ===========================================================================
# 2. request_password_reset -- no email enumeration
# ===========================================================================

def test_request_reset_for_unknown_email_creates_no_token_and_sends_nothing(mocker):
    db = _make_mock_db(user=None)
    send_mock = mocker.patch.object(password_reset_service, "_send_reset_email")

    result = password_reset_service.request_password_reset(db, "nobody@example.com")

    assert result is None
    assert db._added == []
    send_mock.assert_not_called()


# ===========================================================================
# 3. request_password_reset -- token creation for a real account
# ===========================================================================

def test_request_reset_for_known_email_creates_a_hashed_token_and_sends_email(mocker):
    user = _make_user()
    db = _make_mock_db(user=user)
    send_mock = mocker.patch.object(password_reset_service, "_send_reset_email")
    mocker.patch.object(password_reset_service.secrets, "token_urlsafe", return_value="raw-token-value")

    password_reset_service.request_password_reset(db, user.email)

    assert len(db._added) == 1
    token_row = db._added[0]
    assert isinstance(token_row, PasswordResetToken)
    assert token_row.user_id == user.id
    # Only the hash is ever stored -- never the raw token.
    assert token_row.token_hash == hashlib.sha256(b"raw-token-value").hexdigest()
    assert token_row.token_hash != "raw-token-value"
    assert token_row.expires_at > datetime.datetime.utcnow()

    send_mock.assert_called_once_with(user.email, "raw-token-value")


def test_request_reset_expiry_matches_configured_window(mocker):
    user = _make_user()
    db = _make_mock_db(user=user)
    mocker.patch.object(password_reset_service, "_send_reset_email")
    mocker.patch.object(password_reset_service.settings, "password_reset_token_expire_minutes", 45)

    before = datetime.datetime.utcnow()
    password_reset_service.request_password_reset(db, user.email)
    after = datetime.datetime.utcnow()

    token_row = db._added[0]
    assert before + datetime.timedelta(minutes=44) < token_row.expires_at < after + datetime.timedelta(minutes=46)


# ===========================================================================
# 4. reset_password -- success
# ===========================================================================

def test_reset_password_updates_hash_and_marks_token_used(mocker):
    user = _make_user()
    token_row = PasswordResetToken(
        id=1, user_id=user.id,
        token_hash=hashlib.sha256(b"valid-token").hexdigest(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        used_at=None,
    )
    db = _make_mock_db(token_row=token_row, token_row_user=user)
    hash_mock = mocker.patch.object(password_reset_service, "hash_password", return_value="new-hash")

    password_reset_service.reset_password(db, "valid-token", "NewPassword123")

    hash_mock.assert_called_once_with("NewPassword123")
    assert user.password_hash == "new-hash"
    assert token_row.used_at is not None
    db.commit.assert_called_once()


# ===========================================================================
# 5. reset_password -- invalid/expired/used token rejection
# ===========================================================================

def test_reset_password_rejects_unknown_token():
    db = _make_mock_db(token_row=None)
    raised = False
    try:
        password_reset_service.reset_password(db, "no-such-token", "NewPassword123")
    except password_reset_service.InvalidOrExpiredTokenError:
        raised = True
    assert raised


def test_reset_password_rejects_expired_token():
    user = _make_user()
    token_row = PasswordResetToken(
        id=1, user_id=user.id,
        token_hash=hashlib.sha256(b"expired-token").hexdigest(),
        expires_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=1),
        used_at=None,
    )
    db = _make_mock_db(token_row=token_row, token_row_user=user)

    raised = False
    try:
        password_reset_service.reset_password(db, "expired-token", "NewPassword123")
    except password_reset_service.InvalidOrExpiredTokenError:
        raised = True
    assert raised
    assert user.password_hash == "old-hash"  # untouched


def test_reset_password_rejects_already_used_token():
    user = _make_user()
    token_row = PasswordResetToken(
        id=1, user_id=user.id,
        token_hash=hashlib.sha256(b"used-token").hexdigest(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        used_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=5),
    )
    db = _make_mock_db(token_row=token_row, token_row_user=user)

    raised = False
    try:
        password_reset_service.reset_password(db, "used-token", "NewPassword123")
    except password_reset_service.InvalidOrExpiredTokenError:
        raised = True
    assert raised


# ===========================================================================
# 6. Token hashing
# ===========================================================================

def test_hash_token_is_deterministic_sha256():
    assert password_reset_service._hash_token("abc") == hashlib.sha256(b"abc").hexdigest()
    assert password_reset_service._hash_token("abc") == password_reset_service._hash_token("abc")
    assert password_reset_service._hash_token("abc") != password_reset_service._hash_token("xyz")
