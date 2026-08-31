"""
app/api/queue.py
==================

FastAPI routes for the runtime Playback Queue (V0.3). Routes are
intentionally thin, matching `api/playlists.py`: validate input via
Pydantic, delegate to `QueueRepository` (and `PlaylistRepository` for
the "add a whole playlist" route), and translate repository
exceptions into HTTP responses. No SQL/ORM here.

`GET`/`POST`/`DELETE`/reorder routes below never touch the V0.1
`AudioEngine` - they only manage which songs are queued and in what
order, exactly as originally designed.

The one exception is `POST /play`, added for the final V0.3
integration: it is the entry point that actually starts the queue
playing on the (existing, unmodified) V0.1 engine, via the shared
`QueueManager` (`services/queue_manager.py`). Once a track is playing,
all further advancement (natural completion -> next track, manual
stop -> no auto-advance, missing/failed tracks -> skip ahead) is
driven automatically by `QueueManager` reacting to the engine's own
`on_track_end` hook - no polling, and no route needed for it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.repositories.playlist_repository import PlaylistRepository
from ..database.repositories.queue_repository import (
    QueueItemNotFoundError,
    QueueRepository,
    SongNotFoundError,
)
from ..schemas.queue import AddQueueItemRequest, QueueItemOut, ReorderQueueRequest
from ..services.queue_manager import QueueEmptyError, QueueItemNotQueuedError
from ..services.playback_controller import PlaybackControllerError
from .queue_manager_provider import get_queue_manager

router = APIRouter(prefix="/api/queue", tags=["queue"])


# ----------------------------------------------------------------------
# Read
# ----------------------------------------------------------------------

@router.get("", response_model=list[QueueItemOut])
def get_queue(db: Session = Depends(get_db)):
    """Return the full runtime queue, in play order. An empty queue is
    a normal, successful response: `[]`."""
    return [item.to_dict(include_song=True) for item in QueueRepository(db).list_all()]


# ----------------------------------------------------------------------
# Adding
# ----------------------------------------------------------------------

@router.post("", response_model=QueueItemOut, status_code=201)
def add_track(request: AddQueueItemRequest, db: Session = Depends(get_db)):
    """
    Queue a single song from the Music Library (appended to the end by
    default). Pass `play_next: true` to insert it right after whatever
    is currently playing instead.

    The same song can be queued more than once - each call always adds
    a new, distinct queue item rather than merging with an existing
    one for that song.
    """
    repo = QueueRepository(db)
    try:
        item = repo.add_track(request.song_id, play_next=request.play_next)
    except SongNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return item.to_dict(include_song=True)


@router.post("/playlist/{playlist_id}", response_model=list[QueueItemOut], status_code=201)
def add_playlist(playlist_id: int, db: Session = Depends(get_db)):
    """Append every track in a playlist to the end of the queue, in the
    playlist's current order. An empty playlist queues nothing and
    returns `[]`; a missing playlist is a 404."""
    playlist = PlaylistRepository(db).get_with_tracks(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail=f"No playlist with id {playlist_id}.")

    song_ids = [track.song_id for track in playlist.tracks]
    items = QueueRepository(db).add_songs(song_ids)
    db.commit()
    return [item.to_dict(include_song=True) for item in items]


# ----------------------------------------------------------------------
# Removing / clearing
# ----------------------------------------------------------------------

@router.delete("/{queue_item_id}", status_code=204)
def remove_track(queue_item_id: int, db: Session = Depends(get_db)):
    """Remove one item (by `queue_items.id`) from the queue."""
    removed = QueueRepository(db).remove_track(queue_item_id)
    db.commit()
    if not removed:
        raise HTTPException(status_code=404, detail=f"No queue item with id {queue_item_id}.")
    return None


@router.post("/clear", status_code=204)
def clear_queue_explicit(db: Session = Depends(get_db)):
    """Clear upcoming queue items without stopping the song already on air."""
    manager = get_queue_manager()
    manager.clear_pending(db)
    db.commit()
    return None


@router.delete("", status_code=204)
def clear_queue(db: Session = Depends(get_db)):
    """Backward-compatible alias for clearing upcoming queue items."""
    manager = get_queue_manager()
    manager.clear_pending(db)
    db.commit()
    return None


# ----------------------------------------------------------------------
# Reordering
# ----------------------------------------------------------------------

@router.post("/{queue_item_id}/move-up", response_model=QueueItemOut)
def move_track_up(queue_item_id: int, db: Session = Depends(get_db)):
    """Move a queue item one slot earlier. No-op if it's already first."""
    repo = QueueRepository(db)
    try:
        item = repo.move_up(queue_item_id)
    except QueueItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return item.to_dict(include_song=True)


@router.post("/{queue_item_id}/move-down", response_model=QueueItemOut)
def move_track_down(queue_item_id: int, db: Session = Depends(get_db)):
    """Move a queue item one slot later. No-op if it's already last."""
    repo = QueueRepository(db)
    try:
        item = repo.move_down(queue_item_id)
    except QueueItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return item.to_dict(include_song=True)


@router.put("/reorder", response_model=list[QueueItemOut])
def reorder_queue(request: ReorderQueueRequest, db: Session = Depends(get_db)):
    """Re-sequence the whole queue. `queue_item_ids` must be a
    permutation of the queue's current item ids, in the new order."""
    repo = QueueRepository(db)
    try:
        items = repo.reorder(request.queue_item_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return [item.to_dict(include_song=True) for item in items]


# ----------------------------------------------------------------------
# Playback (V0.3 final integration: Queue -> V0.1 AudioEngine)
# ----------------------------------------------------------------------

@router.post("/play")
def play_queue(queue_item_id: int | None = None, db: Session = Depends(get_db)):
    """
    Start the queue playing on the V0.1 AudioEngine.

    - No `queue_item_id`: starts the first `QUEUED` item.
    - `queue_item_id=<id>`: starts that specific (must be `QUEUED`) item.

    A track that turns out to be missing/unplayable is automatically
    marked `FAILED` and skipped in favor of the next `QUEUED` item -
    the response reflects whichever track actually ended up playing.
    From here on, natural completion, manual stop, and further
    failures are all handled automatically by `QueueManager` reacting
    to the engine - no further polling or calls are required.
    """
    manager = get_queue_manager()
    try:
        status = manager.play_from_queue(db, queue_item_id=queue_item_id)
    except QueueEmptyError as exc:
        db.commit()  # persist any FAILED statuses recorded while skipping ahead
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueItemNotQueuedError as exc:
        db.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaybackControllerError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return status
