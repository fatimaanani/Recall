# Search result model, ranked candidates

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.error_log import ErrorLog
    from app.models.evaluation_result import EvaluationResult
    from app.models.generated_clip import GeneratedClip
    from app.models.saved_result import SavedResult
    from app.models.search_query import SearchQuery
    from app.models.transcript_segment import TranscriptSegment
    from app.models.video import Video


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (
        UniqueConstraint("query_id", "rank_position", name="uq_search_results_query_rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    query_id: Mapped[int] = mapped_column(
        ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    # Set null if segment regenerated
    transcript_segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="SET NULL"), nullable=True
    )

    # Captured directly on the row
    matched_start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Final blended score
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    keyword_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Set on "More Info" click
    selected_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    query: Mapped["SearchQuery"] = relationship(back_populates="results")
    video: Mapped["Video"] = relationship(back_populates="search_results")
    transcript_segment: Mapped["TranscriptSegment | None"] = relationship()
    clip: Mapped["GeneratedClip | None"] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )
    # One row per user who bookmarked this result; distinct from selected_at above (which just means opened).
    saved_by: Mapped[list["SavedResult"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )
    error_logs: Mapped[list["ErrorLog"]] = relationship(back_populates="search_result")
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="top_result"
    )

    def __repr__(self) -> str:
        return f"<SearchResult id={self.id} query_id={self.query_id} rank={self.rank_position}>"
