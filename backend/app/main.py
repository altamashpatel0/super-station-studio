"""
app/main.py
============

Application entrypoint: creates the FastAPI app, wires up routers, and
initializes the database on startup.

All four route modules are mounted here: `library` and `playlists`
(V0.2/V0.3, backed by `library_service`, `SongRepository`, and
`PlaylistRepository`, all complete and independently tested) plus
`playback` and `queue` (V0.1/V0.3, backed by the shared `AudioEngine`
and `QueueManager`). This module only wires routers into the app; it
does not implement any request-handling logic of its own.

Startup deliberately constructs the shared `QueueManager` eagerly
(via `get_queue_manager()`), not lazily on first use. `QueueManager`
subscribes to the engine's `on_track_end` hook in its constructor, and
that subscription has to exist *before* the first `stop()`/track
completion happens - including one triggered from the plain
`/api/playback/*` routes, which know nothing about the queue - or
manual-stop/auto-advance bookkeeping would silently be skipped for
whatever happened before the queue was first touched.
"""

from __future__ import annotations

from fastapi import FastAPI

from .api.library import router as library_router
from .api.playback import router as playback_router
from .api.playlists import router as playlists_router
from .api.queue import router as queue_router
from .api.queue_manager_provider import get_queue_manager
from .database.database import init_db

app = FastAPI(title="Music Library / Playout Backend")

app.include_router(library_router)
app.include_router(playback_router)
app.include_router(playlists_router)
app.include_router(queue_router)


@app.on_event("startup")
def _on_startup() -> None:
    init_db()
    get_queue_manager()  # eagerly registers QueueManager on the shared engine


@app.on_event("shutdown")
def _on_shutdown() -> None:
    from .api.engine_provider import get_engine

    get_engine().shutdown()
