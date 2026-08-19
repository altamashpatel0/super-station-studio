"""
app/database/playback_history_models.py

V0.8 Part 3 persistent playback history model.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class PlaybackHistory(Base):
    """
    One real playback session.

    This table intentionally stores a snapshot of content metadata rather than
    foreign keys to Song/Asset so historical rows survive library deletion or
    renaming.
    """

    __tablename__ = "playback_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    ended_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    content_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ENGINE")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_playback_history_started_type", "started_at", "content_type"),
        Index("ix_playback_history_started_status", "started_at", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "content_type": self.content_type,
            "content_id": self.content_id,
            "content_name": self.content_name,
            "file_path": self.file_path,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "source": self.source,
            "error_message": self.error_message,
        }
