# Video model, ownership, source, visibility

from __future__ import annotations

import datetime
import typing

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import MediaSourceType, MediaStatus, MediaVisibility, SubtitleSource

if typing.TYPE_CHECKING:
    from app.models.error_log import ErrorLog
    from app.models.evaluation_test_case import EvaluationTestCase
    from app.models.generated_clip import GeneratedClip
    from app.models.processing_log import ProcessingLog
    from app.models.search_result import SearchResult
    from app.models.transcript_segment import TranscriptSegment
    from app.models.user import User
    from app.models.video_category import VideoCategory


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Set at upload, never edited
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    episode_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    episode_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Set by media processing pipeline
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Duplicate-upload detection
    file_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[MediaStatus] = mapped_column(
        SqlEnum(MediaStatus, name="media_status"),
        nullable=False,
        default=MediaStatus.UPLOADED,
    )
    # Set once at upload
    source_type: Mapped[MediaSourceType] = mapped_column(
        SqlEnum(MediaSourceType, name="media_source_type"), nullable=False
    )
    # Derived from source_type
    visibility: Mapped[MediaVisibility] = mapped_column(
        SqlEnum(MediaVisibility, name="media_visibility"), nullable=False
    )

    subtitle_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subtitle_source: Mapped[SubtitleSource] = mapped_column(
        SqlEnum(SubtitleSource, name="subtitle_source"),
        nullable=False,
        default=SubtitleSource.NONE,
    )
    has_subtitles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # True once every transcript_segments row has an embedding; independent of `status`, since Exact Text search doesn't need embeddings and only Semantic/Speech-to-Text do.
    has_embeddings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True, onupdate=datetime.datetime.utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="videos")
    # Exclusive-owner cascade
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    processing_logs: Mapped[list["ProcessingLog"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    # Multi-parent, DB-level cascade only
    search_results: Mapped[list["SearchResult"]] = relationship(back_populates="video")
    generated_clips: Mapped[list["GeneratedClip"]] = relationship(back_populates="video")
    category_links: Mapped[list["VideoCategory"]] = relationship(back_populates="video")
    error_logs: Mapped[list["ErrorLog"]] = relationship(back_populates="video")
    # RESTRICT, referenced by a test case
    evaluation_test_cases: Mapped[list["EvaluationTestCase"]] = relationship(
        back_populates="expected_video"
    )

    def __repr__(self) -> str:
        return f"<Video id={self.id} title={self.title!r} status={self.status.value}>"
