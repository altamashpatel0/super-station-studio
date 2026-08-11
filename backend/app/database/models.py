"""
app/database/models.py
=======================

SQLAlchemy ORM models for the Music Library (V0.2).

Only one table is needed for V0.2: `songs`. It is deliberately flat
(no separate artists/albums tables yet) because normalizing further is
not required for search/scan/stat features at this stage, and keeping
it flat keeps upserts on rescans simple. Normalizing into
artists/albums tables is a reasonable V0.3+ enhancement if needed.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Song(Base):
    """One row per unique audio file on disk (unique by `file_path`)."""

    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity - `file_path` is the normalized absolute path and is the
    # single source of truth for de-duplication.
    file_path: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata (tags, with filename-derived fallbacks - see metadata_service.py)
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    artist: Mapped[str] = mapped_column(String, nullable=False, index=True)
    album: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    album_artist: Mapped[str] = mapped_column(String, nullable=False, default="")
    genre: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Technical info
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    format: Mapped[str] = mapped_column(String, nullable=False)

    # Library bookkeeping
    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    last_modified: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    last_played: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Soft-availability: a track missing from disk on refresh is disabled
    # rather than deleted, so history/play_count/id references survive.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        Index("ix_songs_artist_album", "artist", "album"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "genre": self.genre,
            "year": self.year,
            "track_number": self.track_number,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "file_size": self.file_size,
            "format": self.format,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "last_played": self.last_played.isoformat() if self.last_played else None,
            "play_count": self.play_count,
            "enabled": self.enabled,
        }


class ScannedFolder(Base):
    """
    Root folders the user has asked the library to watch.

    Recorded so `POST /api/library/rescan` can re-scan every previously
    imported folder without the caller having to remember/re-supply
    paths. Not exposed as its own CRUD surface in V0.2 - it's an
    implementation detail of the scan/rescan/refresh endpoints.
    """

    __tablename__ = "scanned_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folder_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    last_scanned: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
