# Evaluation result model, test case run metrics

from __future__ import annotations

import datetime
import typing

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import SearchBackend

if typing.TYPE_CHECKING:
    from app.models.evaluation_test_case import EvaluationTestCase
    from app.models.search_query import SearchQuery
    from app.models.search_result import SearchResult


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        # PostgreSQL vs Elasticsearch comparison query
        Index("ix_evaluation_results_test_case_search_backend", "test_case_id", "search_backend"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_test_cases.id", ondelete="CASCADE"), nullable=False
    )
    # Set null on delete, record survives query purge
    search_query_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_queries.id", ondelete="SET NULL"), nullable=True
    )
    top_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_results.id", ondelete="SET NULL"), nullable=True
    )

    search_backend: Mapped[SearchBackend] = mapped_column(
        SqlEnum(SearchBackend, name="search_backend"),
        nullable=False,
        default=SearchBackend.POSTGRESQL,
    )

    # Matched within timestamp tolerance
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)

    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    reciprocal_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    evaluated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    test_case: Mapped["EvaluationTestCase"] = relationship(back_populates="results")
    search_query: Mapped["SearchQuery | None"] = relationship(
        back_populates="evaluation_results"
    )
    top_result: Mapped["SearchResult | None"] = relationship(
        back_populates="evaluation_results"
    )

    def __repr__(self) -> str:
        return f"<EvaluationResult id={self.id} test_case_id={self.test_case_id} is_correct={self.is_correct}>"
