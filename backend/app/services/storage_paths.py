from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    """Return the per-user persistent data root for this station instance.

    Electron sets MUSIC_LIBRARY_DATA_DIR to the user's app-data directory.
    Direct development falls back to backend/data so the project remains
    runnable without Electron.
    """
    configured = os.environ.get("MUSIC_LIBRARY_DATA_DIR")
    if configured and configured.strip():
        root = Path(configured.strip()).expanduser()
    else:
        root = Path(__file__).resolve().parents[2] / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def imported_music_root() -> Path:
    root = data_root() / "imported_music"
    root.mkdir(parents=True, exist_ok=True)
    return root


def asset_storage_root() -> Path:
    root = data_root() / "storage" / "assets"
    root.mkdir(parents=True, exist_ok=True)
    return root
