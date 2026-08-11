"""
app/api/library.py
====================

FastAPI routes for the Music Library (V0.2). Routes are intentionally
thin: they validate input via Pydantic, delegate to
`services/library_service.py` and `SongRepository`, and translate
domain errors into HTTP responses. No SQL or filesystem walking here.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.repositories.song_repository import SongRepository
from ..services import library_service
from ..services.library_scanner import InvalidFolderError
from ..schemas.library import (
    LibraryStats,
    RefreshResult,
    ScanJobOut,
    ScanRequest,
    SongOut,
)

router = APIRouter(prefix="/api/library", tags=["library"])


@router.post("/scan", response_model=ScanJobOut, status_code=202)
def scan_library(request: ScanRequest):
    """
    Kick off a recursive scan of `folder_path` on a background thread
    and return immediately with a job handle. Poll
    `GET /api/library/scan/{job_id}` for progress/completion.
    """
    try:
        job = library_service.start_background_scan(request.folder_path)
    except InvalidFolderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job.to_dict()


@router.get("/scan/{job_id}", response_model=ScanJobOut)
def get_scan_status(job_id: str):
    job = library_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No scan job with id '{job_id}'.")
    return job.to_dict()


@router.post("/refresh", response_model=RefreshResult)
def refresh_library(db: Session = Depends(get_db)):
    """Soft-disable any library entries whose files no longer exist on disk."""
    return library_service.refresh_library(db)


@router.post("/rescan", response_model=list[ScanJobOut])
def rescan_library(db: Session = Depends(get_db)):
    """Re-scan every folder previously imported via `POST /api/library/scan`."""
    jobs = library_service.rescan_library(db)
    return [job.to_dict() for job in jobs]


@router.get("/songs", response_model=list[SongOut])
def list_songs(
    enabled_only: bool = Query(False),
    sort_by: str = Query("title", pattern="^(title|artist|album|genre|duration|year|date_added|play_count)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    limit: Optional[int] = Query(None, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = SongRepository(db)
    songs = repo.list_all(
        enabled_only=enabled_only, limit=limit, offset=offset, sort_by=sort_by, sort_dir=sort_dir
    )
    return [song.to_dict() for song in songs]


@router.get("/search", response_model=list[SongOut])
def search_songs(
    q: str = Query(..., min_length=1),
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    repo = SongRepository(db)
    return [song.to_dict() for song in repo.search(q, enabled_only=enabled_only)]


@router.get("/filter", response_model=list[SongOut])
def filter_songs(
    artist: Optional[str] = None,
    album: Optional[str] = None,
    genre: Optional[str] = None,
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    repo = SongRepository(db)
    return [
        song.to_dict()
        for song in repo.filter_songs(artist=artist, album=album, genre=genre, enabled_only=enabled_only)
    ]


@router.get("/stats", response_model=LibraryStats)
def library_stats(db: Session = Depends(get_db)):
    return SongRepository(db).stats()


@router.get("/songs/{song_id}", response_model=SongOut)
def get_song(song_id: int, db: Session = Depends(get_db)):
    song = SongRepository(db).get_by_id(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"No song with id {song_id}.")
    return song.to_dict()


@router.delete("/songs/{song_id}", status_code=204)
def delete_song(song_id: int, db: Session = Depends(get_db)):
    deleted = SongRepository(db).delete(song_id)
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No song with id {song_id}.")
    return None
