"""
app/api/assets.py
===================

FastAPI routes for the Jingle & Advertisement Library. Routes are
intentionally thin, matching `api/library.py` / `api/playlists.py`:
validate input via Pydantic, delegate to `services/asset_service.py`,
and translate domain errors into HTTP responses. No SQL/ORM or
audio-decoding logic here.

V0.5 Part 2: no new endpoints. `priority`/`cooldown_seconds` ride
through the existing create/update routes via the updated
`AssetImportRequest`/`AssetUpdate` schemas.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.models import AudioEngineError

from ..database.database import get_db
from ..database.repositories.asset_repository import AssetNotFoundError, DuplicateAssetError
from ..schemas.assets import AssetImportRequest, AssetOut, AssetUpdate
from ..services import asset_service
from ..services.asset_service import InvalidAssetError

from .asset_playback_provider import (
    get_asset_playback_manager,
)

from ..services.asset_playback_manager import (
    AssetCooldownError,
    AssetPlaybackError,
    AssetPlaybackFileError,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(request: AssetImportRequest, db: Session = Depends(get_db)):
    """Import an existing audio file on disk as a Jingle/Advertisement asset."""
    try:
        asset = asset_service.import_asset(
            db,
            file_path=request.file_path,
            name=request.name,
            asset_type=request.asset_type,
            category=request.category,
            description=request.description,
            priority=request.priority,
            cooldown_seconds=request.cooldown_seconds,
        )
    except InvalidAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DuplicateAssetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AudioEngineError as exc:
        # Covers AudioFileNotFoundError / UnsupportedFormatError / DecodeError.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asset.to_dict()


@router.get("", response_model=list[AssetOut])
def list_assets(
    asset_type: Optional[str] = Query(None, pattern="^(JINGLE|ADVERTISEMENT)$"),
    category: Optional[str] = None,
    search: Optional[str] = None,
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    assets = asset_service.list_assets(
        db, asset_type=asset_type, category=category, search=search, enabled_only=enabled_only
    )
    return [asset.to_dict() for asset in assets]


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"No asset with id {asset_id}.")
    return asset.to_dict()

@router.post("/{asset_id}/play")
def play_asset(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """
    Manually play a Jingle or Advertisement through the
    existing shared AudioEngine.
    """

    try:
        result = (
            get_asset_playback_manager()
            .play_asset(
                db,
                asset_id,
            )
        )

        return result

    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except AssetCooldownError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except AssetPlaybackError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except AudioEngineError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.get("/{asset_id}/playback-status")
def asset_playback_status(
    asset_id: int,
    db: Session = Depends(get_db),
):
    """Return the latest playback state for one asset."""

    try:
        return (
            get_asset_playback_manager()
            .get_status(
                db,
                asset_id,
            )
        )

    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, request: AssetUpdate, db: Session = Depends(get_db)):
    try:
        asset = asset_service.update_asset(
            db,
            asset_id,
            name=request.name,
            category=request.category,
            description=request.description,
            priority=request.priority,
            cooldown_seconds=request.cooldown_seconds,
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asset.to_dict()


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    deleted = asset_service.delete_asset(db, asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No asset with id {asset_id}.")
    return None


@router.post("/{asset_id}/enable", response_model=AssetOut)
def enable_asset(asset_id: int, db: Session = Depends(get_db)):
    try:
        asset = asset_service.enable_asset(db, asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asset.to_dict()


@router.post("/{asset_id}/disable", response_model=AssetOut)
def disable_asset(asset_id: int, db: Session = Depends(get_db)):
    try:
        asset = asset_service.disable_asset(db, asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asset.to_dict()
