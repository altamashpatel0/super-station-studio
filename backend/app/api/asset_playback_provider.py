from __future__ import annotations

from typing import Optional

from ..services.asset_playback_manager import (
    AssetPlaybackManager,
)

from .engine_provider import get_engine


_manager: Optional[AssetPlaybackManager] = None


def get_asset_playback_manager() -> AssetPlaybackManager:
    global _manager

    engine = get_engine()

    # Recreate automatically when tests replace the shared engine.
    if (
        _manager is None
        or _manager.engine is not engine
    ):
        _manager = AssetPlaybackManager(
            engine
        )

    return _manager


def reset_asset_playback_manager() -> None:
    global _manager
    _manager = None