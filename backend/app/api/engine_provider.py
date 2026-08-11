"""
app/api/engine_provider.py
============================

Holds the single shared `src.AudioEngine` instance used by the API
layer. One process -> one audio output channel in V0.2 (matching the
V0.1 engine's own single-output-per-instance design), so this is a
plain module-level singleton rather than a FastAPI dependency that
constructs a new engine per request.

Kept in its own tiny module so both `api/playback.py` and `main.py`
(for startup/shutdown wiring) can import it without a circular import.
"""

from __future__ import annotations

from typing import Optional

from src import AudioEngine

_engine: Optional[AudioEngine] = None


def get_engine() -> AudioEngine:
    global _engine
    if _engine is None:
        _engine = AudioEngine()
    return _engine


def set_engine(engine: Optional[AudioEngine]) -> None:
    """Test/startup hook to inject a specific engine instance (e.g. one
    built with a fake audio_output backend during tests)."""
    global _engine
    _engine = engine


def shutdown_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.shutdown()
        _engine = None
