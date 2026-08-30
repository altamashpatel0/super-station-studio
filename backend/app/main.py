"""
app/main.py
===========
FastAPI application entrypoint and V0.7 station lifecycle wiring.

V0.8 fix:
- Registers the browser folder-import router so
  POST /api/library/import-files is actually available.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.assets import router as assets_router
from .api.asset_upload import router as asset_upload_router
from .api.library import router as library_router
from .api.library_import import router as library_import_router
from .api.live import router as live_router
from .api.live_assist import router as live_assist_router
from .api.playback import router as playback_router
from .api.playlists import router as playlists_router
from .api.reports import router as reports_router
from .api.queue import router as queue_router
from .api.queue_manager_provider import get_queue_manager
from .api.playback_controller_provider import get_playback_controller
from .api.scheduler import router as scheduler_router
from .api.asset_playback_provider import get_asset_playback_manager
from .api.engine_provider import get_engine
from .database.database import init_db
from .services.playback_history import PlaybackHistoryRecorder
from .services.scheduler_recovery import SchedulerFailureRecovery
from .services.scheduler_runtime import SchedulerRuntime
from .services.station_runtime import StationRuntime


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # Construct the central playback authority first. Every production
    # playback service below must use this controller instead of competing
    # directly for the shared AudioEngine.
    engine = get_engine()
    controller = get_playback_controller()

    # Register asset playback after the controller exists so asset starts can
    # also be routed through the same playback authority.
    get_asset_playback_manager()
    history = PlaybackHistoryRecorder(engine)
    app.state.playback_history = history

    # Existing queue listener must be installed before station automation starts.
    queue_manager = get_queue_manager()
    asset_manager = get_asset_playback_manager()

    runtime = SchedulerRuntime(
        engine,
        asset_manager,
        controller=controller,
        queue_manager=queue_manager,
    )
    recovery = SchedulerFailureRecovery(runtime)
    station = StationRuntime(runtime, recovery=recovery)

    app.state.station_runtime = station
    station.start()

    try:
        yield
    finally:
        station.stop()
        history.shutdown()
        engine.shutdown()


app = FastAPI(title="Music Library / Playout Backend", lifespan=lifespan)

# Local Studio frontend runs on Vite (5173) while FastAPI runs on 8000.
# Keep CORS enabled for direct frontend->backend development as well as the
# Vite proxy path. No credentials/cookies are used by this local app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict:
    """Liveness probe used by the test suite and ops tooling."""
    return {"status": "ok"}


# Core application routers
app.include_router(library_router)

# V0.8 browser folder-import bridge.
# This is intentionally separate from the server-side /library/scan route:
# browsers cannot expose the real local Windows folder path to JavaScript.
app.include_router(library_import_router)

app.include_router(live_router)
app.include_router(live_assist_router)
app.include_router(playback_router)
app.include_router(playlists_router)
app.include_router(queue_router)
app.include_router(assets_router)
app.include_router(asset_upload_router)
app.include_router(scheduler_router)
app.include_router(reports_router)
