"""
app/api/library_import.py
=========================

Browser folder-import bridge for the Music Library.

Browsers cannot expose the real local Windows folder path to JavaScript.
The existing scanner intentionally accepts a server-side folder path, so
this route receives the selected MP3/WAV files, stores them in a managed
local import directory, and then runs the existing scanner against that
directory.

V0.8 fixes:
- Provides POST /api/library/import-files.
- Preserves browser relative folder paths.
- Rejects path traversal and unsupported formats.
- Cleans up the temporary batch when the import fails.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.library_service import scan_folder_sync

router = APIRouter(
    prefix="/api/library",
    tags=["music-library-import"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPORTED_MUSIC_ROOT = PROJECT_ROOT / "data" / "imported_music"

ALLOWED_EXTENSIONS = {".mp3", ".wav"}


def _safe_relative_path(value: str) -> Path:
    """
    Convert a browser relative path into a safe local relative Path.

    Example:
        "Album\\Track.mp3"
        -> Path("Album/Track.mp3")
    """
    normalized = (value or "").replace("\\", "/").strip("/")
    candidate = Path(normalized)

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="A relative path is required for every music file.",
        )

    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(
            status_code=400,
            detail="Invalid relative music path.",
        )

    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported audio format: {candidate.name}. "
                "Only MP3 and WAV are supported."
            ),
        )

    return candidate


@router.post("/import-files")
async def import_music_files(
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(...),
):
    """
    Receive browser-selected music files and import them into the library.
    """
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No music files were selected.",
        )

    if len(files) != len(relative_paths):
        raise HTTPException(
            status_code=400,
            detail="Music file/path payload is inconsistent.",
        )

    IMPORTED_MUSIC_ROOT.mkdir(parents=True, exist_ok=True)

    # Every browser import gets an isolated batch directory.
    # This prevents one import from overwriting another import's files.
    batch_dir = IMPORTED_MUSIC_ROOT / uuid.uuid4().hex
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved = 0

    try:
        for upload, relative_name in zip(files, relative_paths):
            relative = _safe_relative_path(
                relative_name or upload.filename or ""
            )

            destination = batch_dir / relative

            # Extra containment check after path construction.
            resolved_batch = batch_dir.resolve()
            resolved_destination = destination.resolve()

            if (
                resolved_destination != resolved_batch
                and resolved_batch not in resolved_destination.parents
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid music file path.",
                )

            destination.parent.mkdir(parents=True, exist_ok=True)

            with destination.open("wb") as output:
                shutil.copyfileobj(upload.file, output)

            saved += 1

    finally:
        for upload in files:
            try:
                await upload.close()
            except Exception:
                pass

    if saved == 0:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="No supported MP3/WAV files were selected.",
        )

    try:
        db = _session_for_scan()

        try:
            job = scan_folder_sync(db, str(batch_dir))
        finally:
            db.close()

        return {
            "status": job.status,
            "processed": job.processed,
            "added": job.added,
            "updated": job.updated,
            "errors": job.errors,
            "error_details": job.error_details[:20],
        }

    except HTTPException:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise

    except Exception as exc:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"Music import failed: {exc}",
        ) from exc


def _session_for_scan():
    """
    Lazily create a normal SQLAlchemy Session.

    Keeping this import local avoids changing the application's existing
    startup/import graph.
    """
    from ..database.database import SessionLocal

    return SessionLocal()
