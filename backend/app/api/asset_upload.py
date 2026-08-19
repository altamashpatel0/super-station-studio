"""
V0.8 Part 2 — browser-safe station asset upload.

The original asset API intentionally imports a file that already exists on the
backend machine. A normal browser file picker cannot expose that local path to
FastAPI. This route receives the actual file bytes, stores them under the
backend's persistent storage/assets directory, then delegates validation and
metadata creation to the existing asset_service.import_asset().
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.models import AudioEngineError
from ..database.database import get_db
from ..database.repositories.asset_repository import DuplicateAssetError
from ..schemas.assets import AssetOut
from ..services import asset_service
from ..services.asset_service import InvalidAssetError

router = APIRouter(prefix="/api/assets", tags=["assets-upload"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "storage" / "assets"


@router.post("/upload", response_model=AssetOut, status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    name: str = Form(...),
    asset_type: str = Form(...),
    category: str = Form(""),
    description: str = Form(""),
    priority: int = Form(0),
    cooldown_seconds: int = Form(0),
    db: Session = Depends(get_db),
):
    """Receive an audio file from the browser and import it as an asset."""
    original_name = Path(file.filename or "asset").name
    suffix = Path(original_name).suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="Audio file must have a file extension.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    size = 0

    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Audio file is too large. Maximum upload size is 100 MB.",
                    )
                output.write(chunk)

        asset = asset_service.import_asset(
            db,
            file_path=str(destination),
            name=name,
            asset_type=asset_type,
            category=category,
            description=description,
            priority=priority,
            cooldown_seconds=cooldown_seconds,
        )
        return asset.to_dict()
    except HTTPException:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise
    except (InvalidAssetError, DuplicateAssetError, AudioEngineError) as exc:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Asset upload failed: {exc}") from exc
    finally:
        await file.close()
