# Admin-to-admin messages

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.user import User


class AdminMessage(Base):
    __tablename__ = "admin_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    sender_admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    sender: Mapped["User"] = relationship(
        foreign_keys=[sender_admin_id], back_populates="sent_admin_messages"
    )
    recipient: Mapped["User"] = relationship(
        foreign_keys=[recipient_admin_id], back_populates="received_admin_messages"
    )

    def __repr__(self) -> str:
        return (
            f"<AdminMessage id={self.id} sender_admin_id={self.sender_admin_id} "
            f"recipient_admin_id={self.recipient_admin_id}>"
        )
