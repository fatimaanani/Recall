# Search query model, one row per search

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import SearchScope, SearchType

if typing.TYPE_CHECKING:
    from app.models.error_log import ErrorLog
    from app.models.evaluation_result import EvaluationResult
    from app.models.search_result import SearchResult
    from app.models.user import User


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Speech-to-text audio query
    original_audio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_query_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Whisper transcription
    transcribed_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    query_type: Mapped[SearchType] = mapped_column(
        SqlEnum(SearchType, name="search_type"), nullable=False
    )
    # My library / shared / both
    search_scope: Mapped[SearchScope] = mapped_column(
        SqlEnum(SearchScope, name="search_scope"),
        nullable=False,
        default=SearchScope.BOTH,
    )

    results_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="search_queries")
    results: Mapped[list["SearchResult"]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )
    error_logs: Mapped[list["ErrorLog"]] = relationship(back_populates="search_query")
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="search_query"
    )

    def __repr__(self) -> str:
        return f"<SearchQuery id={self.id} user_id={self.user_id} type={self.query_type.value}>"
