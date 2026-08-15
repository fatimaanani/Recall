"""Records admin actions taken against users: suspend, reactivate, delete, promote."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User

ACTION_SUSPEND = "suspend"
ACTION_REACTIVATE = "reactivate"
ACTION_DELETE = "delete"
ACTION_PROMOTE = "promote"


def record(db: Session, *, actor: User, target: User, action: str) -> None:
    """Stages the audit row; the caller commits it together with the action itself."""
    db.add(
        AdminAuditLog(
            actor_admin_id=actor.id,
            actor_username=actor.username,
            target_user_id=target.id,
            target_username=target.username,
            action=action,
        )
    )
