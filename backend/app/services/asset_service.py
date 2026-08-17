"""
app/services/asset_service.py
===============================

Business logic layer for the Jingle & Advertisement Library.
Orchestrates file/audio validation and `AssetRepository`, the same
way `library_service.py` orchestrates `library_scanner` and
`SongRepository`. Route handlers in `api/assets.py` should be thin
wrappers around the functions here.

Import validation deliberately reuses the existing, unmodified V0.1
`AudioDecoder` (`src/decoder.py`) - the same decoder the playback
engine and `metadata_service.py`'s fallback path use - rather than
introducing a second audio-reading implementation:

  1. `AudioDecoder.validate_file` checks the path exists and has a
     supported extension.
  2. `AudioDecoder().decode(...)` actually decodes the file, which
     both confirms the audio is genuinely playable (rejecting corrupt
     files) and yields an accurate duration.

This module never touches `songs`, `playlists`, or `queue_items` -
only `AssetRepository` / the `assets` table.

V0.5 Part 2 adds `priority` and `cooldown_seconds` as import/update
fields (both default to 0; `cooldown_seconds` must not be negative -
enforced here as well as at the schema layer, so the invariant holds
regardless of caller). `duration`, `file_path`, and `asset_type`
remain immutable after import - no new way to change them was added.
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from src.decoder import AudioDecoder

from ..database.models import Asset, AssetType
from ..database.repositories.asset_repository import (
    AssetNotFoundError,
    AssetRepository,
    DuplicateAssetError,
)

VALID_ASSET_TYPES = {t.value for t in AssetType}


class InvalidAssetError(Exception):
    """Raised for asset-level validation failures that aren't the
    decoder's concern (empty name, invalid asset_type, bad metadata,
    negative cooldown_seconds)."""


def _normalize_path(file_path: str) -> str:
    from pathlib import Path

    return str(Path(file_path).expanduser().resolve())


def _validate_and_decode(file_path: str) -> float:
    """Validate `file_path` exists, is a supported format, and is
    genuinely decodable audio. Returns the detected duration in
    seconds.

    Raises the underlying `src.models.AudioEngineError` subclasses
    (`AudioFileNotFoundError`, `UnsupportedFormatError`, `DecodeError`)
    unmodified, so callers/tests can distinguish the failure reason
    exactly like the V0.1 engine does.
    """
    decoder = AudioDecoder()
    decoder.validate_file(file_path)  # existence + extension
    decoded = decoder.decode(file_path)  # raises DecodeError if corrupt
    return round(decoded.duration_seconds, 3)


def _validate_common_fields(name: str, asset_type: str) -> None:
    if not name or not name.strip():
        raise InvalidAssetError("Asset name must not be empty.")
    if asset_type not in VALID_ASSET_TYPES:
        supported = ", ".join(sorted(VALID_ASSET_TYPES))
        raise InvalidAssetError(
            f"Invalid asset_type '{asset_type}'. Supported types: {supported}"
        )


def _validate_cooldown(cooldown_seconds: int) -> None:
    if cooldown_seconds < 0:
        raise InvalidAssetError("cooldown_seconds must not be negative.")


def import_asset(
    db: Session,
    *,
    file_path: str,
    name: str,
    asset_type: str,
    category: str = "",
    description: str = "",
    priority: int = 0,
    cooldown_seconds: int = 0,
) -> Asset:
    """
    Import a Jingle/Advertisement asset from an existing audio file on
    disk.

    Validation order matches the spec: file exists -> supported
    extension -> actually decodable -> duration determined -> metadata
    stored. Raises (uncaught here; `api/assets.py` maps these to HTTP
    errors):

      - `InvalidAssetError`: empty name / invalid asset_type / negative
        cooldown_seconds.
      - `AudioFileNotFoundError` / `UnsupportedFormatError` /
        `DecodeError` (from `src.models`): file/audio problems.
      - `DuplicateAssetError`: file already imported as an asset.
    """
    _validate_common_fields(name, asset_type)
    _validate_cooldown(cooldown_seconds)

    normalized_path = _normalize_path(file_path)
    duration = _validate_and_decode(normalized_path)

    repo = AssetRepository(db)
    asset = repo.create(
        {
            "name": name.strip(),
            "asset_type": asset_type,
            "file_path": normalized_path,
            "duration": duration,
            "category": (category or "").strip(),
            "description": description or "",
            "priority": priority,
            "cooldown_seconds": cooldown_seconds,
        }
    )
    db.commit()
    return asset


def get_asset(db: Session, asset_id: int) -> Optional[Asset]:
    return AssetRepository(db).get_by_id(asset_id)


def list_assets(
    db: Session,
    *,
    asset_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    enabled_only: bool = False,
) -> Sequence[Asset]:
    if asset_type is not None and asset_type not in VALID_ASSET_TYPES:
        supported = ", ".join(sorted(VALID_ASSET_TYPES))
        raise InvalidAssetError(
            f"Invalid asset_type '{asset_type}'. Supported types: {supported}"
        )
    return AssetRepository(db).list_all(
        asset_type=asset_type, category=category, search=search, enabled_only=enabled_only
    )


def update_asset(
    db: Session,
    asset_id: int,
    *,
    name: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[int] = None,
    cooldown_seconds: Optional[int] = None,
) -> Asset:
    """Update editable metadata on an asset. `file_path`, `asset_type`,
    and `duration` are immutable after import - changing the
    underlying file/type is a re-import, not an update.

    `priority` and `cooldown_seconds` are editable (playback-management
    metadata); `cooldown_seconds` must not be negative."""
    if name is not None and not name.strip():
        raise InvalidAssetError("Asset name must not be empty.")
    if cooldown_seconds is not None:
        _validate_cooldown(cooldown_seconds)

    fields: dict = {}
    if name is not None:
        fields["name"] = name.strip()
    if category is not None:
        fields["category"] = category.strip()
    if description is not None:
        fields["description"] = description
    if priority is not None:
        fields["priority"] = priority
    if cooldown_seconds is not None:
        fields["cooldown_seconds"] = cooldown_seconds

    asset = AssetRepository(db).update(asset_id, **fields)
    db.commit()
    return asset


def enable_asset(db: Session, asset_id: int) -> Asset:
    asset = AssetRepository(db).set_enabled(asset_id, True)
    db.commit()
    return asset


def disable_asset(db: Session, asset_id: int) -> Asset:
    """Disable an asset. It remains in the database (and remains
    retrievable via GET) - only its `enabled` flag flips, matching the
    Music Library's soft-availability convention."""
    asset = AssetRepository(db).set_enabled(asset_id, False)
    db.commit()
    return asset


def delete_asset(db: Session, asset_id: int) -> bool:
    """Hard-delete an asset row. Only ever touches `assets` - Music
    Library songs, playlists, and the queue are untouched."""
    deleted = AssetRepository(db).delete(asset_id)
    db.commit()
    return deleted


__all__ = [
    "InvalidAssetError",
    "AssetNotFoundError",
    "DuplicateAssetError",
    "import_asset",
    "get_asset",
    "list_assets",
    "update_asset",
    "enable_asset",
    "disable_asset",
    "delete_asset",
]
