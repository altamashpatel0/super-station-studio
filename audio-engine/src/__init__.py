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

V0.4 Part 1 additions (two independent decks, foundation for crossfading):
    - Deck: an AudioEngine with a stable DeckID, otherwise identical API.
    - DeckID: enum identifying a deck (A or B).
    - TwoDeckEngine: owns one Deck A and one Deck B, fully independent.

V0.4 Part 2 additions (crossfade engine):
    - CrossfadeController: ramps two decks' volumes to smoothly
      transition playback from one to the other, without blocking.
    - CrossfadeCurve: LINEAR or EQUAL_POWER volume interpolation.
    - Crossfade exceptions: CrossfadeError and subclasses.

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
from .deck import Deck, DeckID, TwoDeckEngine
from .crossfade import (
    CrossfadeController,
    CrossfadeCurve,
    CrossfadeError,
    InvalidCrossfadeError,
    CrossfadeAlreadyActiveError,
    DEFAULT_CROSSFADE_DURATION_SECONDS,
)

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
    "Deck",
    "DeckID",
    "TwoDeckEngine",
    "CrossfadeController",
    "CrossfadeCurve",
    "CrossfadeError",
    "InvalidCrossfadeError",
    "CrossfadeAlreadyActiveError",
    "DEFAULT_CROSSFADE_DURATION_SECONDS",
]

__version__ = "0.4.0"
