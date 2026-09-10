"""
app/api/queue_manager_provider.py
====================================

Owns the single, shared `QueueManager` (see `services/queue_manager.py`)
for the process, built on top of the same shared `AudioEngine` from
`engine_provider.get_engine()`. Mirrors `engine_provider.py`'s
lazy-singleton pattern so there is exactly one engine and exactly one
manager subscribed to its `on_track_end` hook for the life of the
process.
"""

from __future__ import annotations

from typing import Optional

from ..services.queue_manager import QueueManager
from .engine_provider import get_engine
from .playback_controller_provider import get_playback_controller
from .asset_playback_provider import get_asset_playback_manager

_queue_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager(get_engine(), get_playback_controller(), get_asset_playback_manager())
    return _queue_manager


def reset_queue_manager(manager: Optional[QueueManager] = None) -> QueueManager:
    """
    Test hook: replace the shared manager with `manager` (typically one
    built with `QueueManager(fake_engine)`), or pass nothing to clear
    back to a fresh manager wrapping whatever engine
    `engine_provider.get_engine()` currently returns.

    Application code should never call this.
    """
    global _queue_manager
    _queue_manager = manager
    return get_queue_manager()
