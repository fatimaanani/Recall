from __future__ import annotations

import datetime
import typing

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum as SqlEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import AccountStatus, UserRole

if typing.TYPE_CHECKING:
    from app.models.admin_audit_log import AdminAuditLog
    from app.models.admin_message import AdminMessage
    from app.models.category import Category
    from app.models.error_log import ErrorLog
    from app.models.evaluation_test_case import EvaluationTestCase
    from app.models.password_reset_token import PasswordResetToken
    from app.models.saved_result import SavedResult
    from app.models.search_query import SearchQuery
    from app.models.video import Video

# Default storage quota: 50 GiB
DEFAULT_STORAGE_LIMIT_BYTES = 50 * 1024 * 1024 * 1024


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Hashed only, never returned
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    date_of_birth: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, name="user_role"), nullable=False, default=UserRole.USER
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        SqlEnum(AccountStatus, name="account_status"),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )

    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_limit_bytes: Mapped[int] = mapped_column(
        BigInteger, default=DEFAULT_STORAGE_LIMIT_BYTES, nullable=False
    )

    last_login: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True, onupdate=datetime.datetime.utcnow
    )

    videos: Mapped[list["Video"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    # Exclusive-owner cascade
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    search_queries: Mapped[list["SearchQuery"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # Exclusive-owner cascade -- a user's bookmarks are theirs alone
    saved_results: Mapped[list["SavedResult"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # Multi-parent, DB-level cascade only
    error_logs: Mapped[list["ErrorLog"]] = relationship(back_populates="user")
    # SET NULL, test cases survive admin removal
    created_evaluation_test_cases: Mapped[list["EvaluationTestCase"]] = relationship(
        back_populates="created_by_admin"
    )
    sent_admin_messages: Mapped[list["AdminMessage"]] = relationship(
        foreign_keys="AdminMessage.sender_admin_id", back_populates="sender"
    )
    received_admin_messages: Mapped[list["AdminMessage"]] = relationship(
        foreign_keys="AdminMessage.recipient_admin_id", back_populates="recipient"
    )
    # SET NULL, not CASCADE -- an audit row must outlive the accounts it references (see AdminAuditLog).
    admin_audit_logs_as_actor: Mapped[list["AdminAuditLog"]] = relationship(
        foreign_keys="AdminAuditLog.actor_admin_id", back_populates="actor"
    )
    admin_audit_logs_as_target: Mapped[list["AdminAuditLog"]] = relationship(
        foreign_keys="AdminAuditLog.target_user_id", back_populates="target"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"
