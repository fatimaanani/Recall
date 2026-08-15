# Records admin actions on user accounts (suspend, reactivate, delete, promote); admin-deleting-admin is intentionally unsupported.

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.user import User


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # SET NULL, not CASCADE -- an audit row must outlive the accounts it references.
    actor_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str] = mapped_column(String(80), nullable=False)

    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_username: Mapped[str] = mapped_column(String(80), nullable=False)

    # Plain string, not a SQL enum, matching processing_logs.process_type and error_logs.error_source's convention.
    action: Mapped[str] = mapped_column(String(30), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    actor: Mapped["User | None"] = relationship(
        foreign_keys=[actor_admin_id], back_populates="admin_audit_logs_as_actor"
    )
    target: Mapped["User | None"] = relationship(
        foreign_keys=[target_user_id], back_populates="admin_audit_logs_as_target"
    )

    def __repr__(self) -> str:
        return f"<AdminAuditLog id={self.id} action={self.action!r} target={self.target_username!r}>"
