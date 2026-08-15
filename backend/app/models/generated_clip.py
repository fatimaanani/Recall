# Generated clip model, on-demand clip generation

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.search_result import SearchResult
    from app.models.video import Video


class GeneratedClip(Base):
    __tablename__ = "generated_clips"

    id: Mapped[int] = mapped_column(primary_key=True)

    result_id: Mapped[int] = mapped_column(
        ForeignKey("search_results.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Convenience reference to video
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )

    # Match Resolver boundaries
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)

    # FFmpeg clip generation output
    clip_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    clip_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    result: Mapped["SearchResult"] = relationship(back_populates="clip")
    video: Mapped["Video"] = relationship(back_populates="generated_clips")

    def __repr__(self) -> str:
        return f"<GeneratedClip id={self.id} result_id={self.result_id}>"
