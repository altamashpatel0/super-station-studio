"""
app/api/playlists.py
======================

FastAPI routes for Playlists and playlist track management (V0.3).
Routes are intentionally thin, matching `api/library.py`: validate
input via Pydantic, delegate to `PlaylistRepository`, and translate
repository exceptions into HTTP responses. No SQL/ORM here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.repositories.playlist_repository import (
    PlaylistNotFoundError,
    PlaylistRepository,
    SongNotFoundError,
)
from ..schemas.playlist import (
    AddTrackRequest,
    PlaylistCreate,
    PlaylistDetailOut,
    PlaylistOut,
    PlaylistTrackOut,
    PlaylistUpdate,
    ReorderTracksRequest,
)

router = APIRouter(prefix="/api/playlists", tags=["playlists"])


# ----------------------------------------------------------------------
# Playlist CRUD
# ----------------------------------------------------------------------

@router.post("", response_model=PlaylistOut, status_code=201)
def create_playlist(request: PlaylistCreate, db: Session = Depends(get_db)):
    playlist = PlaylistRepository(db).create(request.name, request.description)
    db.commit()
    return playlist.to_dict()


@router.get("", response_model=list[PlaylistOut])
def list_playlists(db: Session = Depends(get_db)):
    return [p.to_dict() for p in PlaylistRepository(db).list_all()]


@router.get("/{playlist_id}", response_model=PlaylistDetailOut)
def get_playlist(playlist_id: int, db: Session = Depends(get_db)):
    playlist = PlaylistRepository(db).get_with_tracks(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail=f"No playlist with id {playlist_id}.")
    return playlist.to_dict(include_tracks=True)


@router.put("/{playlist_id}", response_model=PlaylistOut)
def update_playlist(playlist_id: int, request: PlaylistUpdate, db: Session = Depends(get_db)):
    repo = PlaylistRepository(db)
    try:
        playlist = repo.update(playlist_id, name=request.name, description=request.description)
    except PlaylistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return playlist.to_dict()


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, db: Session = Depends(get_db)):
    deleted = PlaylistRepository(db).delete(playlist_id)
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No playlist with id {playlist_id}.")
    return None


# ----------------------------------------------------------------------
# Track management
# ----------------------------------------------------------------------

@router.post("/{playlist_id}/tracks", response_model=PlaylistTrackOut, status_code=201)
def add_track(playlist_id: int, request: AddTrackRequest, db: Session = Depends(get_db)):
    """Add either a Song or a Promo occurrence to a playlist."""
    repo = PlaylistRepository(db)
    if not request.is_valid_reference:
        raise HTTPException(status_code=400, detail="Provide exactly one of song_id or asset_id.")
    try:
        if request.asset_id is not None:
            track = repo.add_asset(playlist_id, request.asset_id, request.position)
        else:
            track = repo.add_track(playlist_id, request.song_id, request.position)
    except PlaylistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SongNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return track.to_dict(include_song=True)


@router.delete("/{playlist_id}/tracks/{track_id}", status_code=204)
def remove_track(playlist_id: int, track_id: int, db: Session = Depends(get_db)):
    """Remove one track (by `playlist_tracks.id`) from the playlist."""
    repo = PlaylistRepository(db)
    if repo.get_by_id(playlist_id) is None:
        raise HTTPException(status_code=404, detail=f"No playlist with id {playlist_id}.")

    removed = repo.remove_track(playlist_id, track_id)
    db.commit()
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"No track with id {track_id} in playlist {playlist_id}.",
        )
    return None


@router.put("/{playlist_id}/tracks/reorder", response_model=list[PlaylistTrackOut])
def reorder_tracks(playlist_id: int, request: ReorderTracksRequest, db: Session = Depends(get_db)):
    """Re-sequence a playlist's tracks. `track_ids` must be a permutation
    of the playlist's current `playlist_tracks.id` values, in the new order."""
    repo = PlaylistRepository(db)
    try:
        tracks = repo.reorder_tracks(playlist_id, request.track_ids)
    except PlaylistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return [t.to_dict(include_song=True) for t in tracks]


@router.delete("/{playlist_id}/tracks", status_code=204)
def clear_tracks(playlist_id: int, db: Session = Depends(get_db)):
    """Remove every track from a playlist (the playlist itself is kept)."""
    repo = PlaylistRepository(db)
    try:
        repo.clear_tracks(playlist_id)
    except PlaylistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return None
