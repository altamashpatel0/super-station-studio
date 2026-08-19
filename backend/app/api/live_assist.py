"""
app/api/live_assist.py
======================

V0.8 Part 2 — Live Assist control surface.

The existing /api/playback/* and /api/assets/* endpoints remain the
canonical transport/asset playback APIs. This module only exposes the
operator-facing live-assist status and volume control, using the exact
process-wide AudioEngine owned by engine_provider.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.models import AudioEngineError, InvalidVolumeError
from .engine_provider import get_engine

router = APIRouter(prefix="/api/live-assist", tags=["live-assist"])


class VolumeRequest(BaseModel):
    volume: float = Field(ge=0.0, le=1.0)


@router.get("/status")
def live_assist_status() -> dict:
    """Return the real shared AudioEngine transport status."""
    return get_engine().get_status().to_dict()


@router.post("/volume")
def set_volume(request: VolumeRequest) -> dict:
    """Set the real shared AudioEngine volume in the range 0..1."""
    try:
        engine = get_engine()
        engine.set_volume(request.volume)
        return engine.get_status().to_dict()
    except InvalidVolumeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AudioEngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
