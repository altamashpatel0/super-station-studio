"""
app/schemas/playlist.py
=========================

Pydantic request/response models for Playlists (V0.3 foundation).
Mirrors the split used by `schemas/library.py`: these are the wire
formats, kept independent of the SQLAlchemy models in
`database/models.py`.

No API routes consume these yet - this module is part of the
database/backend foundation landed ahead of the playlist API and
queue work.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .library import SongOut


class PlaylistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""


class PlaylistUpdate(BaseModel):
    """All fields optional - only provided fields are changed."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class PlaylistOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    track_count: int = 0


class PlaylistTrackOut(BaseModel):
    id: int
    playlist_id: int
    song_id: Optional[int] = None
    asset_id: Optional[int] = None
    track_type: str = "SONG"
    position: int
    added_at: Optional[str] = None
    song: Optional[SongOut] = None
    asset: Optional[dict] = None


class PlaylistDetailOut(PlaylistOut):
    """A playlist with its ordered tracks included."""

    tracks: list[PlaylistTrackOut] = []


class AddTrackRequest(BaseModel):
    song_id: Optional[int] = None
    asset_id: Optional[int] = None
    # Zero-based insert position; omit to append to the end.
    position: Optional[int] = Field(None, ge=0)

    @property
    def is_valid_reference(self) -> bool:
        return (self.song_id is not None) ^ (self.asset_id is not None)


class ReorderTracksRequest(BaseModel):
    """`track_ids` must be a permutation of the playlist's current
    `playlist_tracks.id` values, in the desired new order."""

    track_ids: list[int] = Field(..., min_length=1)
