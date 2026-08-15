# Processing log model, pipeline stage tracking

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import ProcessingStatus

if typing.TYPE_CHECKING:
    from app.models.video import Video


class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )

    # Free text stage name
    process_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # One row per stage attempt
    status: Mapped[ProcessingStatus] = mapped_column(
        SqlEnum(ProcessingStatus, name="processing_status"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    video: Mapped["Video"] = relationship(back_populates="processing_logs")

    def __repr__(self) -> str:
        return f"<ProcessingLog id={self.id} video_id={self.video_id} process_type={self.process_type!r} status={self.status.value}>"
