"""
app/api/live.py
===============

V0.8 Part 1 — read-only Live Station Monitor API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..services.live_station_monitor import LiveStationMonitor

router = APIRouter(prefix="/api/live", tags=["live"])
_monitor = LiveStationMonitor()


@router.get("/status")
def live_status(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Return a real-time snapshot for the Live Monitor UI."""
    station_runtime = getattr(request.app.state, "station_runtime", None)
    if station_runtime is None:
        raise HTTPException(
            status_code=503,
            detail="Station runtime is not available.",
        )

    return _monitor.snapshot(db, station_runtime)
