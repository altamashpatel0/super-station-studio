"""app/api/library.py - Music Library routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.repositories.song_repository import SongRepository
from ..services import library_service
from ..services.library_scanner import InvalidFolderError
from ..schemas.library import LibraryStats, RefreshResult, ScanJobOut, ScanRequest, SongOut

router = APIRouter(prefix="/api/library", tags=["library"])

@router.post("/scan", response_model=ScanJobOut, status_code=202)
def scan_library(request: ScanRequest):
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
    return library_service.refresh_library(db)

@router.post("/rescan", response_model=list[ScanJobOut])
def rescan_library(db: Session = Depends(get_db)):
    jobs = library_service.rescan_library(db)
    return [job.to_dict() for job in jobs]

@router.get("/songs", response_model=list[SongOut])
def list_songs(enabled_only: bool = Query(False), sort_by: str = Query("title", pattern="^(title|artist|album|genre|duration|year|date_added|play_count)$"), sort_dir: str = Query("asc", pattern="^(asc|desc)$"), limit: Optional[int] = Query(None, ge=1, le=5000), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    repo = SongRepository(db)
    songs = repo.list_all(enabled_only=enabled_only, limit=limit, offset=offset, sort_by=sort_by, sort_dir=sort_dir)
    return [song.to_dict() for song in songs]

@router.get("/search", response_model=list[SongOut])
def search_songs(q: str = Query(..., min_length=1), enabled_only: bool = Query(False), db: Session = Depends(get_db)):
    return [song.to_dict() for song in SongRepository(db).search(q, enabled_only=enabled_only)]

@router.get("/filter", response_model=list[SongOut])
def filter_songs(artist: Optional[str] = None, album: Optional[str] = None, genre: Optional[str] = None, enabled_only: bool = Query(False), db: Session = Depends(get_db)):
    repo = SongRepository(db)
    return [song.to_dict() for song in repo.filter_songs(artist=artist, album=album, genre=genre, enabled_only=enabled_only)]

@router.get("/stats", response_model=LibraryStats)
def library_stats(db: Session = Depends(get_db)):
    return SongRepository(db).stats()

def _image_from_audio(file_path: str):
    """Return (bytes, mime) for embedded cover art, or None."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(file_path)
        if audio is None:
            return None
        tags = getattr(audio, "tags", None)

        # MP3 / ID3 APIC
        if tags is not None and hasattr(tags, "getall"):
            pictures = tags.getall("APIC")
            if pictures:
                picture = pictures[0]
                data = getattr(picture, "data", None)
                mime = getattr(picture, "mime", None) or "image/jpeg"
                if data:
                    return bytes(data), mime

        # FLAC / OGG pictures
        pictures = getattr(audio, "pictures", None)
        if pictures:
            picture = pictures[0]
            data = getattr(picture, "data", None)
            mime = getattr(picture, "mime", None) or "image/jpeg"
            if data:
                return bytes(data), mime

        # MP4/M4A covr atoms
        if tags is not None and hasattr(tags, "get"):
            covers = tags.get("covr")
            if covers:
                data = bytes(covers[0])
                mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
                return data, mime
    except Exception:
        return None
    return None

@router.get("/songs/{song_id}/artwork")
def get_song_artwork(song_id: int, db: Session = Depends(get_db)):
    song = SongRepository(db).get_by_id(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"No song with id {song_id}.")
    artwork = _image_from_audio(song.file_path)
    if artwork is None:
        raise HTTPException(status_code=404, detail="This audio file has no embedded artwork.")
    data, mime = artwork
    return Response(content=data, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})

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
