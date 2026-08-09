"""
models.py
=========

Shared data models, enums, and exceptions used across the audio engine.

Keeping these in a single module means `engine.py`, `player.py`,
`decoder.py`, and `audio_output.py` all speak the same "language" of
states and errors, and the future FastAPI layer can import this module
alone to build request/response schemas (e.g. with Pydantic) without
depending on the playback internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PlayerState(str, Enum):
    """
    Discrete states of the player's finite state machine.

    IDLE     - No track loaded. Initial state / state after engine reset.
    LOADING  - A file is currently being validated/decoded.
    PLAYING  - Audio is actively being output.
    PAUSED   - Playback is suspended; position is retained.
    STOPPED  - A track is loaded (or finished) but not playing;
               position is at 0 (or wherever stop left it).
    ERROR    - The last operation failed. `PlaybackStatus.error_message`
               holds details. The engine remains usable; loading a new
               file clears the error.
    """

    IDLE = "IDLE"
    LOADING = "LOADING"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class TrackEndReason(str, Enum):
    """
    Why a PLAYING track transitioned away from PLAYING.

    Exposed separately from PlayerState because a "track finished
    naturally" event is semantically different from a "user pressed
    stop" event, even though both currently land the player in
    STOPPED. Future automatic next-track logic (V0.2+) should only
    react to COMPLETED.
    """

    COMPLETED = "COMPLETED"          # Reached end of audio data naturally.
    MANUAL_STOP = "MANUAL_STOP"      # stop() called by the caller.
    ERROR = "ERROR"                  # Playback aborted due to an error.


@dataclass(frozen=True)
class PlaybackStatus:
    """
    An immutable snapshot of the engine's playback status.

    This is the shape that will eventually be serialized directly as a
    FastAPI/Pydantic response model, so keep it flat and JSON-friendly.
    """

    state: PlayerState
    file_path: Optional[str]
    position_seconds: float
    duration_seconds: float
    volume: float
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a plain, JSON-serializable dictionary representation."""
        return {
            "state": self.state.value,
            "file_path": self.file_path,
            "position_seconds": round(self.position_seconds, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "volume": round(self.volume, 3),
            "error_message": self.error_message,
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AudioEngineError(Exception):
    """Base class for all audio-engine-specific errors.

    Catching this single type is enough for callers (including the
    future FastAPI layer) to know "something about audio playback
    failed" without the process crashing.
    """


class AudioFileNotFoundError(AudioEngineError):
    """Raised when the requested audio file does not exist on disk."""


class UnsupportedFormatError(AudioEngineError):
    """Raised when a file's extension/container is not supported."""


class DecodeError(AudioEngineError):
    """Raised when a file exists and has a supported extension but
    cannot actually be decoded (corrupt data, unreadable stream, etc.)."""


class AudioOutputError(AudioEngineError):
    """Raised when the audio output device cannot be opened, started,
    or written to."""


class InvalidStateError(AudioEngineError):
    """Raised when an operation is requested that is not valid for the
    player's current state (e.g. calling resume() while STOPPED)."""


class InvalidSeekError(AudioEngineError):
    """Raised when a seek position is out of range or otherwise invalid."""


class InvalidVolumeError(AudioEngineError):
    """Raised when a volume value is outside the valid [0.0, 1.0] range."""
