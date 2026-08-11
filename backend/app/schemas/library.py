"""
app/schemas/library.py
========================

Pydantic request/response models for the Music Library API. Kept
separate from the SQLAlchemy models (`database/models.py`) so the wire
format can evolve independently of the storage schema.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SongOut(BaseModel):
    id: int
    file_path: str
    file_name: str
    title: str
    artist: str
    album: str
    album_artist: str
    genre: str
    year: Optional[int] = None
    track_number: Optional[int] = None
    duration: float
    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None
    file_size: int
    format: str
    date_added: Optional[str] = None
    last_modified: Optional[str] = None
    last_played: Optional[str] = None
    play_count: int
    enabled: bool


class ScanRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)


class ScanJobOut(BaseModel):
    job_id: str
    folder_path: str
    status: str
    processed: int
    added: int
    updated: int
    errors: int
    error_details: list[str]
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    failure_reason: Optional[str] = None


class RefreshResult(BaseModel):
    checked: int
    disabled: int


class LibraryStats(BaseModel):
    total_songs: int
    artists: int
    albums: int
    genres: int
    total_duration_seconds: float
    available: int
    unavailable: int


class PlayRequest(BaseModel):
    song_id: int
