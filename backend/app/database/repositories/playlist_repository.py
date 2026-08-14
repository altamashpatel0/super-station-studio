"""
app/database/repositories/playlist_repository.py
====================================================

All SQL/ORM operations on `playlists` and `playlist_tracks` live here,
mirroring `song_repository.py`. A future API layer (`api/playlists.py`)
calls into this repository rather than building queries itself.

Order is maintained as a dense, zero-based `position` sequence per
playlist and is entirely owned by this repository - `position` is
never taken as-is from a caller and written straight through, so the
sequence can't be left sparse or duplicated by a partial update.
"""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Playlist, PlaylistTrack, Song


class PlaylistNotFoundError(Exception):
    """Raised when an operation references a playlist id that doesn't exist."""


class SongNotFoundError(Exception):
    """Raised when an operation references a song id that doesn't exist."""


class PlaylistRepository:
    """Thin data-access layer around `playlists` / `playlist_tracks`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Playlist CRUD
    # ------------------------------------------------------------------

    def create(self, name: str, description: str = "") -> Playlist:
        now = datetime.datetime.utcnow()
        playlist = Playlist(name=name, description=description, created_at=now, updated_at=now)
        self.db.add(playlist)
        self.db.flush()
        return playlist

    def get_by_id(self, playlist_id: int) -> Optional[Playlist]:
        return self.db.get(Playlist, playlist_id)

    def get_with_tracks(self, playlist_id: int) -> Optional[Playlist]:
        """Fetch a playlist with its tracks (and each track's song) eager-loaded."""
        stmt = (
            select(Playlist)
            .where(Playlist.id == playlist_id)
            .options(selectinload(Playlist.tracks).selectinload(PlaylistTrack.song))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self) -> Sequence[Playlist]:
        stmt = select(Playlist).order_by(Playlist.name.asc())
        return self.db.execute(stmt).scalars().all()

    def update(
        self, playlist_id: int, *, name: Optional[str] = None, description: Optional[str] = None
    ) -> Playlist:
        playlist = self.get_by_id(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(f"No playlist with id {playlist_id}.")
        if name is not None:
            playlist.name = name
        if description is not None:
            playlist.description = description
        playlist.updated_at = datetime.datetime.utcnow()
        self.db.flush()
        return playlist

    def delete(self, playlist_id: int) -> bool:
        """Delete a playlist and (via cascade) all of its playlist_tracks rows."""
        playlist = self.get_by_id(playlist_id)
        if playlist is None:
            return False
        self.db.delete(playlist)
        self.db.flush()
        return True

    # ------------------------------------------------------------------
    # Track membership / order
    # ------------------------------------------------------------------

    def list_tracks(self, playlist_id: int) -> Sequence[PlaylistTrack]:
        if self.get_by_id(playlist_id) is None:
            raise PlaylistNotFoundError(f"No playlist with id {playlist_id}.")
        stmt = (
            select(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def add_track(self, playlist_id: int, song_id: int, position: Optional[int] = None) -> PlaylistTrack:
        """
        Insert `song_id` into the playlist at `position` (default:
        append to the end). The same song may be added more than once,
        including to the same playlist.

        Raises `PlaylistNotFoundError` / `SongNotFoundError` for
        invalid references up front, as a clear, catchable
        application-level check in addition to the DB-level foreign
        keys enforced via SQLite's `PRAGMA foreign_keys=ON`.
        """
        if self.get_by_id(playlist_id) is None:
            raise PlaylistNotFoundError(f"No playlist with id {playlist_id}.")
        if self.db.get(Song, song_id) is None:
            raise SongNotFoundError(f"No song with id {song_id}.")

        existing = list(self.list_tracks(playlist_id))
        count = len(existing)
        insert_at = count if position is None else min(max(position, 0), count)

        # Shift everything from insert_at onward down one slot to make room.
        for track in existing[insert_at:]:
            track.position += 1

        track = PlaylistTrack(
            playlist_id=playlist_id,
            song_id=song_id,
            position=insert_at,
            added_at=datetime.datetime.utcnow(),
        )
        self.db.add(track)
        self._touch(playlist_id)
        self.db.flush()
        return track

    def remove_track(self, playlist_id: int, playlist_track_id: int) -> bool:
        """Remove one playlist_track row and close the resulting gap in positions."""
        track = self.db.get(PlaylistTrack, playlist_track_id)
        if track is None or track.playlist_id != playlist_id:
            return False

        removed_position = track.position
        self.db.delete(track)
        self.db.flush()

        for remaining in self.list_tracks(playlist_id):
            if remaining.position > removed_position:
                remaining.position -= 1
        self._touch(playlist_id)
        self.db.flush()
        return True

    def reorder_tracks(self, playlist_id: int, ordered_track_ids: list[int]) -> Sequence[PlaylistTrack]:
        """
        Re-sequence a playlist's tracks to match `ordered_track_ids`
        exactly. `ordered_track_ids` must be a permutation of the
        playlist's current `playlist_tracks.id` values.
        """
        if self.get_by_id(playlist_id) is None:
            raise PlaylistNotFoundError(f"No playlist with id {playlist_id}.")

        current = list(self.list_tracks(playlist_id))
        current_ids = {t.id for t in current}
        if len(ordered_track_ids) != len(current) or set(ordered_track_ids) != current_ids:
            raise ValueError(
                "ordered_track_ids must be a permutation of the playlist's current track ids."
            )

        by_id = {t.id: t for t in current}
        for index, track_id in enumerate(ordered_track_ids):
            by_id[track_id].position = index
        self._touch(playlist_id)
        self.db.flush()
        return self.list_tracks(playlist_id)

    def clear_tracks(self, playlist_id: int) -> int:
        """Remove every track from a playlist. Returns the number removed."""
        if self.get_by_id(playlist_id) is None:
            raise PlaylistNotFoundError(f"No playlist with id {playlist_id}.")
        tracks = self.list_tracks(playlist_id)
        count = len(tracks)
        for track in tracks:
            self.db.delete(track)
        self._touch(playlist_id)
        self.db.flush()
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _touch(self, playlist_id: int) -> None:
        playlist = self.get_by_id(playlist_id)
        if playlist is not None:
            playlist.updated_at = datetime.datetime.utcnow()
