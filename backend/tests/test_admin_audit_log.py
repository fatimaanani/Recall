"""
test_admin_audit_log.py

Unit tests for the admin audit log: admin_audit_log_service.py directly,
plus the four admin_service.py call sites (suspend, reactivate, delete,
promote) that stage an AdminAuditLog row alongside their existing
action. Mocked DB session -- no Postgres needed.

1. Shared helpers
2. admin_audit_log_service.record
3. admin_service.suspend_user / reactivate_user stage the right action
4. admin_service.delete_user_by_admin stages before deleting
5. admin_service.promote_user_to_admin stages the right action
6. Admin-deleting-admin remains unsupported
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from app.enums import UserRole
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User
from app.services import admin_audit_log_service, admin_service


def _make_user(**overrides) -> User:
    # created_at is required (AdminUserOut.created_at: datetime.datetime,
    # not Optional) -- a real row always has it via the column's own
    # default=datetime.datetime.utcnow, but that default only fires on a
    # real INSERT/flush, never on a bare User(...) construction. This
    # mocked-db suite never flushes for real, so it must be set explicitly
    # here, same convention as every timestamp column elsewhere in this
    # codebase (naive UTC, not timezone-aware).
    defaults = dict(
        id=1, full_name="Test User", username="testuser", email="test@example.com",
        password_hash="x", role=UserRole.USER, created_at=datetime.datetime.utcnow(),
    )
    defaults.update(overrides)
    return User(**defaults)


def _make_mock_db(target_user=None):
    mock_db = MagicMock()
    added: list = []
    mock_db.add.side_effect = added.append
    mock_db.commit.side_effect = lambda: None
    mock_db.refresh.side_effect = lambda obj: None
    mock_db._added = added

    q = mock_db.query.return_value
    q.filter.return_value = q
    q.first.return_value = target_user
    q.scalar.return_value = 0

    return mock_db


def _audit_rows(db) -> list[AdminAuditLog]:
    return [obj for obj in db._added if isinstance(obj, AdminAuditLog)]


# ===========================================================================
# 2. admin_audit_log_service.record
# ===========================================================================

def test_record_stages_a_row_with_actor_and_target_snapshots():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user")
    db = _make_mock_db()

    admin_audit_log_service.record(db, actor=actor, target=target, action="suspend")

    assert len(db._added) == 1
    entry = db._added[0]
    assert isinstance(entry, AdminAuditLog)
    assert entry.actor_admin_id == 1
    assert entry.actor_username == "admin_a"
    assert entry.target_user_id == 2
    assert entry.target_username == "target_user"
    assert entry.action == "suspend"
    # record() only stages -- it must never commit on its own, callers
    # commit it together with the action being recorded.
    db.commit.assert_not_called()


# ===========================================================================
# 3. suspend_user / reactivate_user
# ===========================================================================

def test_suspend_user_stages_suspend_action():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user")
    db = _make_mock_db(target_user=target)

    admin_service.suspend_user(db, actor, target.id)

    rows = _audit_rows(db)
    assert len(rows) == 1
    assert rows[0].action == admin_audit_log_service.ACTION_SUSPEND
    assert rows[0].actor_admin_id == actor.id
    assert rows[0].target_user_id == target.id


def test_reactivate_user_stages_reactivate_action():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user")
    db = _make_mock_db(target_user=target)

    admin_service.reactivate_user(db, actor, target.id)

    rows = _audit_rows(db)
    assert len(rows) == 1
    assert rows[0].action == admin_audit_log_service.ACTION_REACTIVATE


def test_suspend_user_not_found_stages_no_audit_row():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    db = _make_mock_db(target_user=None)

    raised = False
    try:
        admin_service.suspend_user(db, actor, 999)
    except admin_service.UserNotFoundError:
        raised = True
    assert raised
    assert _audit_rows(db) == []


# ===========================================================================
# 4. delete_user_by_admin
# ===========================================================================

def test_delete_user_stages_delete_action_before_deleting():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user")
    db = _make_mock_db(target_user=target)

    admin_service.delete_user_by_admin(db, actor, target.id, "target_user")

    rows = _audit_rows(db)
    assert len(rows) == 1
    assert rows[0].action == admin_audit_log_service.ACTION_DELETE
    assert rows[0].target_username == "target_user"
    db.delete.assert_called_once_with(target)


def test_delete_user_username_mismatch_stages_no_audit_row():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user")
    db = _make_mock_db(target_user=target)

    raised = False
    try:
        admin_service.delete_user_by_admin(db, actor, target.id, "wrong_username")
    except admin_service.UsernameMismatchError:
        raised = True
    assert raised
    assert _audit_rows(db) == []
    db.delete.assert_not_called()


# ===========================================================================
# 5. promote_user_to_admin
# ===========================================================================

def test_promote_user_stages_promote_action():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="target_user", email="target@example.com", role=UserRole.USER)
    db = _make_mock_db(target_user=target)

    admin_service.promote_user_to_admin(db, actor, target.email)

    rows = _audit_rows(db)
    assert len(rows) == 1
    assert rows[0].action == admin_audit_log_service.ACTION_PROMOTE
    assert rows[0].target_user_id == target.id


def test_promote_already_admin_stages_no_audit_row():
    actor = _make_user(id=1, username="admin_a", role=UserRole.ADMIN)
    target = _make_user(id=2, username="already_admin", email="already@example.com", role=UserRole.ADMIN)
    db = _make_mock_db(target_user=target)

    raised = False
    try:
        admin_service.promote_user_to_admin(db, actor, target.email)
    except admin_service.AlreadyAdminError:
        raised = True
    assert raised
    assert _audit_rows(db) == []


# ===========================================================================
# 6. Admin-deleting-admin remains unsupported
# ===========================================================================

def test_admin_target_is_never_found_by_get_target_user_or_none():
    # _get_target_user_or_none only ever matches role == USER -- confirms
    # admin-deleting-admin is not supported.
    admin_target = _make_user(id=3, username="other_admin", role=UserRole.ADMIN)
    db = _make_mock_db(target_user=admin_target)
    # _get_target_user_or_none re-checks user.role itself after the query
    # returns a row -- simulate that by using the real function against a
    # db whose query stub returns an admin-role user.
    found = admin_service._get_target_user_or_none(db, admin_target.id)
    assert found is None
