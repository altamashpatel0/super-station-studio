"""
engine.py
=========

`AudioEngine` is the single public entry point this package exposes to
the outside world (manual test scripts today; the FastAPI backend in
V0.2/V0.3). It wraps `Player` and presents a clean, stable, framework
agnostic API:

    React UI -> Electron -> FastAPI -> AudioEngine -> Windows Audio Output

Nothing in this module imports FastAPI, HTTP, or JSON - it just needs
to be trivially *callable from* an HTTP layer later. Every method
returns plain Python values (or the `PlaybackStatus` dataclass, which
already has a `.to_dict()` for JSON serialization), and every error is
raised as a documented `AudioEngineError` subclass rather than a raw
exception, so a future FastAPI exception handler can map them to clean
HTTP responses.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .decoder import AudioDecoder
from .audio_output import AudioOutputBase
from .models import PlaybackStatus, PlayerState, TrackEndReason
from .player import Player

logger = logging.getLogger(__name__)

TrackCompleteCallback = Callable[[str], None]


class AudioEngine:
    """
    High-level facade over the audio playback subsystem.

    One `AudioEngine` instance corresponds to one audio output channel.
    A future multi-studio setup could run multiple `AudioEngine`
    instances side by side; that is out of scope for V0.1.
    """

    def __init__(
        self,
        audio_output: Optional[AudioOutputBase] = None,
        decoder: Optional[AudioDecoder] = None,
    ) -> None:
        """
        Args:
            audio_output: Optional injected output backend. Defaults to
                the real sound-card backend; tests inject a fake one.
            decoder: Optional injected decoder. Defaults to the real
                PyAV-backed decoder.
        """
        self._player = Player(decoder=decoder, audio_output=audio_output)
        self._on_track_complete_listeners: list[TrackCompleteCallback] = []

        self._player.on_track_end(self._handle_track_end)

    # ------------------------------------------------------------------
    # Loading & transport - the surface FastAPI will call directly.
    # ------------------------------------------------------------------

    def load_track(self, file_path: str) -> PlaybackStatus:
        """Load a local MP3/WAV file. Raises `AudioEngineError` subtypes
        on missing files, unsupported formats, or decode failures."""
        self._player.load(file_path)
        return self.get_status()

    def play(self) -> PlaybackStatus:
        """Start or resume-from-stopped playback of the loaded track."""
        self._player.play()
        return self.get_status()

    def preload_track(self, file_path: str) -> None:
        """Best-effort background decode for a future queue track."""
        self._player.preload(file_path)

    def pause(self) -> PlaybackStatus:
        """Pause playback, retaining position."""
        self._player.pause()
        return self.get_status()

    def resume(self) -> PlaybackStatus:
        """Resume playback after a pause."""
        self._player.resume()
        return self.get_status()

    def stop(self) -> PlaybackStatus:
        """Stop playback and reset position to the start."""
        self._player.stop()
        return self.get_status()

    def seek(self, seconds: float) -> PlaybackStatus:
        """Seek to an absolute position (in seconds) in the loaded track."""
        self._player.seek(seconds)
        return self.get_status()

    def set_volume(self, volume: float) -> PlaybackStatus:
        """Set output volume, 0.0 (silent) to 1.0 (full)."""
        self._player.set_volume(volume)
        return self.get_status()

    def get_volume(self) -> float:
        return self._player.get_volume()

    # ------------------------------------------------------------------
    # Status & introspection
    # ------------------------------------------------------------------

    def get_status(self) -> PlaybackStatus:
        """Return a full snapshot of current playback status."""
        return self._player.get_status()

    def get_state(self) -> PlayerState:
        return self._player.get_status().state

    def is_playing(self) -> bool:
        return self.get_state() == PlayerState.PLAYING

    # ------------------------------------------------------------------
    # Event hooks - the extension points for V0.2's scheduler
    # ------------------------------------------------------------------

    def on_track_complete(self, callback: TrackCompleteCallback) -> None:
        """
        Register a callback invoked as `callback(file_path)` whenever
        the currently loaded track finishes playing *naturally* (i.e.
        reaches the end of the audio, as opposed to being manually
        stopped).

        This is the intended hook for V0.2's automatic next-track
        playback: a scheduler can register here, call `load_track()`
        with the next item, and call `play()`, without any changes to
        this engine.
        """
        self._on_track_complete_listeners.append(callback)

    def on_state_change(self, callback: Callable[[PlayerState, PlayerState], None]) -> None:
        """Register a callback invoked as `callback(old_state, new_state)`."""
        self._player.on_state_change(callback)

    def on_track_end(self, callback: Callable[[TrackEndReason], None]) -> None:
        """Register a callback for *any* end-of-playback event
        (completed, manually stopped, or error) with its reason."""
        self._player.on_track_end(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Release the audio output device. Call on application exit."""
        self._player.shutdown()

    def __enter__(self) -> "AudioEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_track_end(self, reason: TrackEndReason) -> None:
        if reason != TrackEndReason.COMPLETED:
            return
        status = self.get_status()
        file_path = status.file_path
        if file_path is None:
            return
        for callback in list(self._on_track_complete_listeners):
            try:
                callback(file_path)
            except Exception:  # pragma: no cover - defensive
                logger.exception("on_track_complete listener raised an exception")
