# Evaluation test case model, labeled test set

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import SearchScope, SearchType

if typing.TYPE_CHECKING:
    from app.models.evaluation_result import EvaluationResult
    from app.models.user import User
    from app.models.video import Video

DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 5.0


class EvaluationTestCase(Base):
    __tablename__ = "evaluation_test_cases"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Set null on delete, preserves test-case history
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_query_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    search_type: Mapped[SearchType] = mapped_column(
        SqlEnum(SearchType, name="search_type"), nullable=False
    )
    search_scope: Mapped[SearchScope] = mapped_column(
        SqlEnum(SearchScope, name="search_scope"),
        nullable=False,
        default=SearchScope.BOTH,
    )

    # RESTRICT, video still referenced by test case
    expected_video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False
    )
    expected_start_time: Mapped[float] = mapped_column(Float, nullable=False)
    expected_end_time: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp_tolerance_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=DEFAULT_TIMESTAMP_TOLERANCE_SECONDS
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    created_by_admin: Mapped["User | None"] = relationship(
        back_populates="created_evaluation_test_cases"
    )
    expected_video: Mapped["Video"] = relationship(back_populates="evaluation_test_cases")
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EvaluationTestCase id={self.id} test_name={self.test_name!r}>"
