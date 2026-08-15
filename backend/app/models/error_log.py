# Error log model, search/query failures

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.search_query import SearchQuery
    from app.models.search_result import SearchResult
    from app.models.user import User
    from app.models.video import Video


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    search_query_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=True
    )
    search_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_results.id", ondelete="CASCADE"), nullable=True
    )
    # Clip-generation failures
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=True
    )

    # e.g. exact_text_search, semantic_search
    error_source: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    user: Mapped["User | None"] = relationship(back_populates="error_logs")
    search_query: Mapped["SearchQuery | None"] = relationship(back_populates="error_logs")
    search_result: Mapped["SearchResult | None"] = relationship(back_populates="error_logs")
    video: Mapped["Video | None"] = relationship(back_populates="error_logs")

    def __repr__(self) -> str:
        return f"<ErrorLog id={self.id} error_source={self.error_source!r}>"
