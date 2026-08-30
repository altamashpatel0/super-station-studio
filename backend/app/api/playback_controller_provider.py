from __future__ import annotations

from typing import Optional

from ..services.playback_controller import PlaybackController
from .engine_provider import get_engine

_controller: Optional[PlaybackController] = None


def get_playback_controller() -> PlaybackController:
    global _controller
    if _controller is None:
        _controller = PlaybackController(get_engine(), use_two_deck=False)
    return _controller


def reset_playback_controller(
    controller: Optional[PlaybackController] = None,
) -> PlaybackController:
    global _controller
    _controller = controller
    return get_playback_controller()
