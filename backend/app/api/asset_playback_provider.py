from __future__ import annotations

from typing import Optional

from ..services.asset_playback_manager import AssetPlaybackManager
from .engine_provider import get_engine
from .playback_controller_provider import get_playback_controller

_manager: Optional[AssetPlaybackManager] = None

def get_asset_playback_manager() -> AssetPlaybackManager:
    global _manager
    engine = get_engine()
    controller = get_playback_controller()
    if (
        _manager is None
        or _manager.engine is not engine
    ):
        _manager = AssetPlaybackManager(engine, controller)
    return _manager

def reset_asset_playback_manager(
    manager: Optional[AssetPlaybackManager] = None,
) -> AssetPlaybackManager:
    global _manager
    _manager = manager
    return get_asset_playback_manager()
