# Video-category junction model

from __future__ import annotations

import datetime
import typing

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if typing.TYPE_CHECKING:
    from app.models.category import Category
    from app.models.video import Video


class VideoCategory(Base):
    __tablename__ = "video_categories"

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )

    assigned_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    video: Mapped["Video"] = relationship(back_populates="category_links")
    category: Mapped["Category"] = relationship(back_populates="video_links")

    def __repr__(self) -> str:
        return f"<VideoCategory video_id={self.video_id} category_id={self.category_id}>"
