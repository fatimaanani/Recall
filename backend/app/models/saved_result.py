# Saved result model, deliberate per-user bookmark of a generated scene

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.search_result import SearchResult
    from app.models.user import User


# A SavedResult row only exists when the user explicitly bookmarks a result, distinct from SearchResult.selected_at (which just means it was opened); video and clip are reachable via search_result rather than duplicated here.
class SavedResult(Base):
    __tablename__ = "saved_results"
    __table_args__ = (
        UniqueConstraint("user_id", "search_result_id", name="uq_saved_results_user_result"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    search_result_id: Mapped[int] = mapped_column(
        ForeignKey("search_results.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="saved_results")
    result: Mapped["SearchResult"] = relationship(back_populates="saved_by")

    def __repr__(self) -> str:
        return f"<SavedResult id={self.id} user_id={self.user_id} search_result_id={self.search_result_id}>"
