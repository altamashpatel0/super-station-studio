"""
app/api/playback.py
=====================

Thin FastAPI wrapper around the existing, unmodified V0.1 `AudioEngine`
(`src/engine.py`). This module contains no playback logic of its own -
it only translates HTTP requests into calls on a single shared
`AudioEngine` instance and `AudioEngineError` subclasses into HTTP
errors.

    React (Music Library "Play") -> Electron -> here -> src.AudioEngine

Selecting a song in the Music Library UI resolves to a `song_id`,
which this module looks up via `SongRepository` to get the on-disk
`file_path`, then hands to the *same* engine used by V0.1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.models import AudioEngineError

from ..database.database import get_db
from ..database.repositories.song_repository import SongRepository
from ..schemas.library import PlayRequest
from .engine_provider import get_engine
from .playback_controller_provider import get_playback_controller
from ..services.playback_controller import PlaybackControllerError, PlaybackSource

router = APIRouter(prefix="/api/playback", tags=["playback"])


@router.post("/play-song")
def play_song(request: PlayRequest, db: Session = Depends(get_db)):
    """Load and play a library track by its database id via the V0.1 engine."""
    repo = SongRepository(db)
    song = repo.get_by_id(request.song_id)
    if song is None:
        raise HTTPException(status_code=404, detail=f"No song with id {request.song_id}.")
    if not song.enabled:
        raise HTTPException(status_code=409, detail="This track is marked unavailable (file missing).")

    controller = get_playback_controller()
    try:
        status = controller.start_track(
            PlaybackSource.MANUAL,
            song.file_path,
        )
    except (AudioEngineError, PlaybackControllerError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo.record_play(song.id)
    db.commit()
    return status.to_dict()


@router.post("/pause")
def pause():
    try:
        return get_playback_controller().engine.pause().to_dict()
    except AudioEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/resume")
def resume():
    try:
        return get_playback_controller().engine.resume().to_dict()
    except AudioEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def stop():
    try:
        return get_playback_controller().stop(PlaybackSource.MANUAL).to_dict()
    except PlaybackControllerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AudioEngineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status")
def status():
    return get_playback_controller().get_status()
