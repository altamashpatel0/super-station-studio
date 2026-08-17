"""
app/database/repositories/asset_repository.py
================================================

All SQL/ORM operations on the `assets` table (Jingle & Advertisement
Library) live here, mirroring `song_repository.py` /
`playlist_repository.py`. Route handlers and `services/asset_service.py`
never build queries themselves - they call into this repository.

V0.5 Part 2 change: `list_all` now orders by `priority` (descending)
first, falling back to the existing V0.5 Part 1 ordering (`name` asc,
then `id` asc as a final tiebreaker so the ordering is fully
deterministic) for assets that share a priority. No other behavior
changes.
"""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Asset


class AssetNotFoundError(Exception):
    """Raised when an operation references an asset id that doesn't exist."""


class DuplicateAssetError(Exception):
    """Raised when importing a file_path that's already an asset."""


class AssetRepository:
    """Thin data-access layer around the `assets` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_by_id(self, asset_id: int) -> Optional[Asset]:
        return self.db.get(Asset, asset_id)

    def get_by_path(self, file_path: str) -> Optional[Asset]:
        stmt = select(Asset).where(Asset.file_path == file_path)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(
        self,
        *,
        asset_type: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        enabled_only: bool = False,
    ) -> Sequence[Asset]:
        """List assets, optionally filtered by type/category/search text.

        All filters can be combined (e.g. `asset_type=JINGLE` plus
        `search=...`), matching the `GET /api/assets` query-parameter
        contract.

        Ordering is deterministic: higher `priority` sorts first; ties
        fall back to the original V0.5 Part 1 ordering (`name` asc),
        with `id` asc as a final tiebreaker so equal-priority,
        equal-name rows still come back in a stable order.
        """
        stmt = select(Asset)
        if asset_type:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if category:
            stmt = stmt.where(Asset.category == category)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Asset.name.ilike(like),
                    Asset.category.ilike(like),
                    Asset.description.ilike(like),
                )
            )
        if enabled_only:
            stmt = stmt.where(Asset.enabled.is_(True))
        stmt = stmt.order_by(Asset.priority.desc(), Asset.name.asc(), Asset.id.asc())
        return self.db.execute(stmt).scalars().all()

    def search(self, query: str, *, enabled_only: bool = False) -> Sequence[Asset]:
        return self.list_all(search=query, enabled_only=enabled_only)

    def filter_by_type(self, asset_type: str, *, enabled_only: bool = False) -> Sequence[Asset]:
        return self.list_all(asset_type=asset_type, enabled_only=enabled_only)

    def filter_by_category(self, category: str, *, enabled_only: bool = False) -> Sequence[Asset]:
        return self.list_all(category=category, enabled_only=enabled_only)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create(self, data: dict) -> Asset:
        """Insert a new asset. Raises `DuplicateAssetError` if
        `data['file_path']` is already imported."""
        if self.get_by_path(data["file_path"]) is not None:
            raise DuplicateAssetError(
                f"Asset already imported for file_path '{data['file_path']}'."
            )
        now = datetime.datetime.utcnow()
        asset = Asset(**data, created_at=now, updated_at=now, enabled=True)
        self.db.add(asset)
        self.db.flush()
        return asset

    def update(self, asset_id: int, **fields) -> Asset:
        """Update metadata fields on an existing asset. Only keys
        present in `fields` are changed; `None` values are applied
        as-is (callers should omit fields they don't want touched)."""
        asset = self.get_by_id(asset_id)
        if asset is None:
            raise AssetNotFoundError(f"No asset with id {asset_id}.")
        for key, value in fields.items():
            setattr(asset, key, value)
        asset.updated_at = datetime.datetime.utcnow()
        self.db.flush()
        return asset

    def set_enabled(self, asset_id: int, enabled: bool) -> Asset:
        asset = self.get_by_id(asset_id)
        if asset is None:
            raise AssetNotFoundError(f"No asset with id {asset_id}.")
        asset.enabled = enabled
        asset.updated_at = datetime.datetime.utcnow()
        self.db.flush()
        return asset

    def delete(self, asset_id: int) -> bool:
        """Delete an asset. Only ever touches the `assets` table -
        Music Library (`songs`), playlists, and the queue are entirely
        unrelated tables and are never affected."""
        asset = self.get_by_id(asset_id)
        if asset is None:
            return False
        self.db.delete(asset)
        self.db.flush()
        return True
