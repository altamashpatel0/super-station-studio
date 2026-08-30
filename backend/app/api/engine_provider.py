"""
app/api/engine_provider.py
============================

Owns the single, shared, unmodified V0.1 `AudioEngine` instance used
by every consumer of playback in this process:

    api/playback.py   -> direct "play this library song right now"
    services/queue_manager.py -> V0.3 queue-driven playback

One process = one `AudioEngine` = one audio output device, exactly as
V0.1 intended ("one `AudioEngine` instance corresponds to one audio
output channel" - see `src/engine.py`). This module's only job is to
construct that single instance lazily and hand the same object to
every caller.
"""

from __future__ import annotations

from typing import Optional

from src.engine import AudioEngine

_engine: Optional[AudioEngine] = None


def get_engine() -> AudioEngine:
    """Return the process-wide `AudioEngine`, constructing it on first use."""
    global _engine
    if _engine is None:
        _engine = AudioEngine()
    return _engine


def reset_engine(engine: Optional[AudioEngine] = None) -> AudioEngine:
    """
    Test hook: replace the shared engine with `engine` (typically one
    built with a fake decoder/audio_output so tests don't touch real
    audio hardware or real files), or pass nothing to clear back to a
    fresh real `AudioEngine`.

    Application code should never call this - it exists purely so
    `tests/conftest.py` can isolate the engine (and whatever is
    subscribed to its `on_track_end` hook) between test cases.
    """
    global _engine
    _engine = engine
    try:
        from .playback_controller_provider import reset_playback_controller
        reset_playback_controller(None)
    except ImportError:
        # Keep the low-level engine provider usable in isolated audio-engine tests.
        pass
    return get_engine()


def set_engine(engine: Optional[AudioEngine]) -> AudioEngine:
    """
    Backward-compatible alias for `reset_engine`.

    Older tests (e.g. `tests/test_playback_api.py`) install their own
    fake-backed engine via this name. Kept as a thin wrapper so both
    call sites work against the same single `_engine` global.
    """
    return reset_engine(engine)


def shutdown_engine() -> None:
    """
    Backward-compatible test hook: shut down whatever engine is
    currently installed (if any) and clear it back to `None`, so the
    next `get_engine()` call constructs a fresh real `AudioEngine`.
    """
    global _engine
    if _engine is not None:
        _engine.shutdown()
    _engine = None
    try:
        from .playback_controller_provider import reset_playback_controller
        reset_playback_controller(None)
    except ImportError:
        pass
