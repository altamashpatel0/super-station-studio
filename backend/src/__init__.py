"""
Super Station Studio - Core Audio Engine
==========================================

A standalone, production-grade audio playback engine for the Super Station
Studio radio automation system.

This package is intentionally decoupled from any web framework so that it
can be embedded in the future FastAPI backend (V0.2/V0.3) without changes:

    React UI -> Electron -> FastAPI -> AudioEngine -> Windows Audio Output

Public API surface (stable, intended for FastAPI to consume):
    - AudioEngine: high-level orchestration class, one instance per output.
    - PlayerState: enum of possible player states.
    - PlaybackStatus: immutable snapshot of engine status.
    - TrackEndReason: why a track stopped (completed, manual stop, error).
    - Exceptions: AudioEngineError and subclasses.

Nothing else in this package should be considered part of the stable API.
"""

from .models import (
    PlayerState,
    PlaybackStatus,
    TrackEndReason,
    AudioEngineError,
    AudioFileNotFoundError,
    UnsupportedFormatError,
    DecodeError,
    AudioOutputError,
    InvalidStateError,
    InvalidSeekError,
    InvalidVolumeError,
)
from .engine import AudioEngine

__all__ = [
    "AudioEngine",
    "PlayerState",
    "PlaybackStatus",
    "TrackEndReason",
    "AudioEngineError",
    "AudioFileNotFoundError",
    "UnsupportedFormatError",
    "DecodeError",
    "AudioOutputError",
    "InvalidStateError",
    "InvalidSeekError",
    "InvalidVolumeError",
]

__version__ = "0.1.0"
