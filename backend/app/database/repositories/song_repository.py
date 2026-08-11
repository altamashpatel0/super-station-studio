"""
app/database/repositories/song_repository.py
==============================================

All SQL/ORM operations on the `songs` table live here. Route handlers
and services never build queries themselves - they call into this
repository, which keeps `library.py` (API layer) and
`library_service.py` (business logic) free of SQL.
"""

from __future__ import annotations

import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Song


class SongRepository:
    """Thin data-access layer around the `songs` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_by_id(self, song_id: int) -> Optional[Song]:
        return self.db.get(Song, song_id)

    def get_by_path(self, file_path: str) -> Optional[Song]:
        stmt = select(Song).where(Song.file_path == file_path)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        *,
        enabled_only: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
        sort_by: str = "title",
        sort_dir: str = "asc",
    ) -> Sequence[Song]:
        stmt = select(Song)
        if enabled_only:
            stmt = stmt.where(Song.enabled.is_(True))

        sort_column = getattr(Song, sort_by, Song.title)
        stmt = stmt.order_by(sort_column.desc() if sort_dir == "desc" else sort_column.asc())

        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        return self.db.execute(stmt).scalars().all()

    def search(
        self,
        query: str,
        *,
        enabled_only: bool = False,
        limit: Optional[int] = None,
    ) -> Sequence[Song]:
        like = f"%{query.strip()}%"
        stmt = select(Song).where(
            or_(
                Song.title.ilike(like),
                Song.artist.ilike(like),
                Song.album.ilike(like),
                Song.genre.ilike(like),
            )
        )
        if enabled_only:
            stmt = stmt.where(Song.enabled.is_(True))
        stmt = stmt.order_by(Song.title.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.db.execute(stmt).scalars().all()

    def filter_songs(
        self,
        *,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        enabled_only: bool = False,
    ) -> Sequence[Song]:
        stmt = select(Song)
        if artist:
            stmt = stmt.where(Song.artist == artist)
        if album:
            stmt = stmt.where(Song.album == album)
        if genre:
            stmt = stmt.where(Song.genre == genre)
        if enabled_only:
            stmt = stmt.where(Song.enabled.is_(True))
        stmt = stmt.order_by(Song.title.asc())
        return self.db.execute(stmt).scalars().all()

    def all_paths(self) -> set[str]:
        stmt = select(Song.file_path).where(Song.enabled.is_(True))
        return set(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def upsert(self, data: dict) -> tuple[Song, bool]:
        """
        Insert a new song, or update an existing one matched by
        `file_path`. Returns `(song, created)`.
        """
        existing = self.get_by_path(data["file_path"])
        now = datetime.datetime.utcnow()

        if existing is None:
            song = Song(**data, date_added=now, last_modified=now, enabled=True)
            self.db.add(song)
            self.db.flush()
            return song, True

        for key, value in data.items():
            setattr(existing, key, value)
        existing.last_modified = now
        existing.enabled = True
        self.db.flush()
        return existing, False

    def set_enabled(self, song_id: int, enabled: bool) -> Optional[Song]:
        song = self.get_by_id(song_id)
        if song is None:
            return None
        song.enabled = enabled
        self.db.flush()
        return song

    def disable_by_paths(self, file_paths: Iterable[str]) -> int:
        """Soft-disable songs whose paths are no longer on disk. Returns count."""
        count = 0
        for path in file_paths:
            song = self.get_by_path(path)
            if song is not None and song.enabled:
                song.enabled = False
                count += 1
        self.db.flush()
        return count

    def delete(self, song_id: int) -> bool:
        song = self.get_by_id(song_id)
        if song is None:
            return False
        self.db.delete(song)
        self.db.flush()
        return True

    def record_play(self, song_id: int) -> Optional[Song]:
        song = self.get_by_id(song_id)
        if song is None:
            return None
        song.play_count += 1
        song.last_played = datetime.datetime.utcnow()
        self.db.flush()
        return song

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        total_songs = self.db.execute(select(func.count(Song.id))).scalar_one()
        available = self.db.execute(
            select(func.count(Song.id)).where(Song.enabled.is_(True))
        ).scalar_one()
        unavailable = total_songs - available

        artists = self.db.execute(
            select(func.count(func.distinct(Song.artist))).where(Song.artist != "")
        ).scalar_one()
        albums = self.db.execute(
            select(func.count(func.distinct(Song.album))).where(Song.album != "")
        ).scalar_one()
        genres = self.db.execute(
            select(func.count(func.distinct(Song.genre))).where(Song.genre != "")
        ).scalar_one()
        total_duration = self.db.execute(select(func.sum(Song.duration))).scalar_one() or 0.0

        return {
            "total_songs": total_songs,
            "artists": artists,
            "albums": albums,
            "genres": genres,
            "total_duration_seconds": round(total_duration, 2),
            "available": available,
            "unavailable": unavailable,
        }
