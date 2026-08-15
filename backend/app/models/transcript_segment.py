# Transcript segment model, searchable spoken content

from __future__ import annotations

import typing

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Enum as SqlEnum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import SubtitleSource

if typing.TYPE_CHECKING:
    from app.models.video import Video

# Sentence Transformers all-MiniLM-L6-v2 embedding size
EMBEDDING_DIMENSIONS = 384


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )

    # Seconds into the video
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # pgvector similarity search
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    # PostgreSQL full-text search, generated automatically from `text` by Postgres (STORED) so it never drifts out of sync; uses the 'simple' config since transcripts mix Arabic and English.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', text)", persisted=True),
        nullable=True,
    )

    # Uploaded / embedded / whisper
    source: Mapped[SubtitleSource] = mapped_column(
        SqlEnum(SubtitleSource, name="subtitle_source"), nullable=False
    )

    video: Mapped["Video"] = relationship(back_populates="transcript_segments")

    def __repr__(self) -> str:
        return f"<TranscriptSegment id={self.id} video_id={self.video_id}>"
