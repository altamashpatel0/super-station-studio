"""
player.py
=========

The `Player` class owns the playback state machine and the transport
controls (play/pause/resume/stop/seek/volume). It coordinates between
`AudioDecoder` (gets samples into memory) and `AudioOutputBase` (gets
samples out to the sound card), but knows nothing about how either of
those is implemented internally.

Thread-safety note: `AudioOutputBase` implementations pull audio from
a background (real-time) thread via `_read_frames`. All shared state
(`_position_frames`, `_volume`, `_state`) is guarded by `_lock` to keep
the public API (called from the "main"/control thread) and the audio
callback thread consistent.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

import numpy as np

from .audio_output import AudioOutputBase, SoundDeviceOutput
from .decoder import AudioDecoder, DecodedAudio
from .models import (
    AudioEngineError,
    InvalidSeekError,
    InvalidStateError,
    InvalidVolumeError,
    PlaybackStatus,
    PlayerState,
    TrackEndReason,
)

logger = logging.getLogger(__name__)

StateChangeCallback = Callable[[PlayerState, PlayerState], None]
TrackEndCallback = Callable[[TrackEndReason], None]

# States from which play()/resume() type calls are meaningfully valid.
_VALID_TRANSITIONS = {
    "play": {PlayerState.STOPPED, PlayerState.PAUSED},
    "pause": {PlayerState.PLAYING},
    "resume": {PlayerState.PAUSED},
    "stop": {PlayerState.PLAYING, PlayerState.PAUSED, PlayerState.STOPPED},
    "seek": {PlayerState.PLAYING, PlayerState.PAUSED, PlayerState.STOPPED},
}


class Player:
    """
    Controls playback of a single, currently-loaded audio track.

    This class is intentionally single-track: multi-track sequencing
    (playlists, clock wheels, crossfading) is out of scope for V0.1 and
    belongs in a future scheduler built on top of `AudioEngine`.
    """

    def __init__(
        self,
        decoder: Optional[AudioDecoder] = None,
        audio_output: Optional[AudioOutputBase] = None,
    ) -> None:
        self._decoder = decoder or AudioDecoder()
        self._output = audio_output or SoundDeviceOutput()

        self._lock = threading.RLock()
        self._state = PlayerState.IDLE
        self._audio: Optional[DecodedAudio] = None
        self._position_frames = 0
        self._volume = 1.0
        self._error_message: Optional[str] = None

        self._state_change_listeners: List[StateChangeCallback] = []
        self._track_end_listeners: List[TrackEndCallback] = []

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def on_state_change(self, callback: StateChangeCallback) -> None:
        """Register a callback invoked as `callback(old_state, new_state)`
        every time the player's state changes."""
        self._state_change_listeners.append(callback)

    def on_track_end(self, callback: TrackEndCallback) -> None:
        """Register a callback invoked as `callback(reason)` whenever
        playback stops, whether by completion, manual stop, or error.

        This is the extension point the future scheduler (V0.2+) will
        use to trigger automatic next-track playback on
        `TrackEndReason.COMPLETED`.
        """
        self._track_end_listeners.append(callback)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, file_path: str) -> None:
        """
        Load and decode an audio file, leaving the player STOPPED
        (i.e. ready to play) at position 0.

        Never raises silently into a crash: on failure the player is
        left in the ERROR state with `error_message` set, and the
        original exception is re-raised for the caller to handle.
        """
        with self._lock:
            self._set_state(PlayerState.LOADING)
            self._output.stop()

        try:
            decoded = self._decoder.decode(file_path)
        except AudioEngineError as exc:
            with self._lock:
                self._error_message = str(exc)
                self._audio = None
                self._set_state(PlayerState.ERROR)
            logger.error("Failed to load '%s': %s", file_path, exc)
            raise
        except Exception as exc:  # pragma: no cover - defensive catch-all
            with self._lock:
                self._error_message = str(exc)
                self._audio = None
                self._set_state(PlayerState.ERROR)
            logger.exception("Unexpected error loading '%s'", file_path)
            raise

        with self._lock:
            self._audio = decoded
            self._position_frames = 0
            self._error_message = None
            self._set_state(PlayerState.STOPPED)

        logger.info(
            "Loaded '%s' (%.2fs, %d Hz, %d ch)",
            file_path,
            decoded.duration_seconds,
            decoded.sample_rate,
            decoded.channels,
        )

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    def preload(self, file_path: str) -> None:
        """Best-effort background decode of a future track."""
        self._decoder.preload(file_path)

    def play(self) -> None:
        """Start (or restart from the current position) playback."""
        with self._lock:
            self._require_loaded()
            if self._state not in _VALID_TRANSITIONS["play"]:
                raise InvalidStateError(
                    f"Cannot play() while in state {self._state.value}."
                )
            assert self._audio is not None

            try:
                self._output.open(self._audio.sample_rate, self._audio.channels)
                self._output.start(self._read_frames, self._on_output_finished)
            except AudioEngineError as exc:
                self._error_message = str(exc)
                self._set_state(PlayerState.ERROR)
                self._notify_track_end(TrackEndReason.ERROR)
                raise

            self._set_state(PlayerState.PLAYING)

    def pause(self) -> None:
        """Suspend playback, retaining the current position."""
        with self._lock:
            if self._state not in _VALID_TRANSITIONS["pause"]:
                raise InvalidStateError(
                    f"Cannot pause() while in state {self._state.value}."
                )
            try:
                self._output.pause()
            except AudioEngineError as exc:
                self._error_message = str(exc)
                self._set_state(PlayerState.ERROR)
                raise
            self._set_state(PlayerState.PAUSED)

    def resume(self) -> None:
        """Resume playback after a pause, from the retained position."""
        with self._lock:
            if self._state not in _VALID_TRANSITIONS["resume"]:
                raise InvalidStateError(
                    f"Cannot resume() while in state {self._state.value}."
                )
            try:
                self._output.resume()
            except AudioEngineError as exc:
                self._error_message = str(exc)
                self._set_state(PlayerState.ERROR)
                raise
            self._set_state(PlayerState.PLAYING)

    def stop(self) -> None:
        """Stop playback and reset the position to the beginning."""
        with self._lock:
            if self._state not in _VALID_TRANSITIONS["stop"]:
                raise InvalidStateError(
                    f"Cannot stop() while in state {self._state.value}."
                )
            was_playing = self._state in (PlayerState.PLAYING, PlayerState.PAUSED)
            self._output.stop()
            self._position_frames = 0
            self._set_state(PlayerState.STOPPED)

        if was_playing:
            self._notify_track_end(TrackEndReason.MANUAL_STOP)

    def seek(self, seconds: float) -> None:
        """
        Move the playback position to `seconds` from the start of the
        current track.

        Raises:
            InvalidSeekError: if `seconds` is negative or beyond the
                track's duration, or if no track is loaded.
        """
        with self._lock:
            self._require_loaded()
            assert self._audio is not None

            if self._state not in _VALID_TRANSITIONS["seek"]:
                raise InvalidStateError(
                    f"Cannot seek() while in state {self._state.value}."
                )

            if seconds < 0 or seconds > self._audio.duration_seconds:
                raise InvalidSeekError(
                    f"Seek position {seconds:.2f}s is out of range "
                    f"[0, {self._audio.duration_seconds:.2f}]s."
                )

            self._position_frames = int(seconds * self._audio.sample_rate)
            self._position_frames = min(self._position_frames, self._audio.total_frames)

    def set_volume(self, volume: float) -> None:
        """
        Set playback volume as a float in [0.0, 1.0].

        Raises:
            InvalidVolumeError: if `volume` is outside [0.0, 1.0].
        """
        if not (0.0 <= volume <= 1.0):
            raise InvalidVolumeError(
                f"Volume must be between 0.0 and 1.0, got {volume}."
            )
        with self._lock:
            self._volume = float(volume)

    def get_volume(self) -> float:
        with self._lock:
            return self._volume

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> PlaybackStatus:
        with self._lock:
            duration = self._audio.duration_seconds if self._audio else 0.0
            position = (
                self._position_frames / float(self._audio.sample_rate)
                if self._audio
                else 0.0
            )
            return PlaybackStatus(
                state=self._state,
                file_path=self._audio.file_path if self._audio else None,
                position_seconds=position,
                duration_seconds=duration,
                volume=self._volume,
                error_message=self._error_message,
            )

    def shutdown(self) -> None:
        """Release the audio output device. Call when the player (or
        the process) is being torn down."""
        with self._lock:
            self._output.stop()
            self._output.close()
            self._set_state(PlayerState.IDLE)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_loaded(self) -> None:
        if self._audio is None:
            raise InvalidStateError("No track is loaded.")

    def _set_state(self, new_state: PlayerState) -> None:
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        for callback in list(self._state_change_listeners):
            try:
                callback(old_state, new_state)
            except Exception:  # pragma: no cover - defensive
                logger.exception("State change listener raised an exception")

    def _notify_track_end(self, reason: TrackEndReason) -> None:
        for callback in list(self._track_end_listeners):
            try:
                callback(reason)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Track end listener raised an exception")

    def _read_frames(self, frame_count: int) -> np.ndarray:
        """
        Called from the audio output's real-time thread to pull the
        next block of samples. Applies volume scaling and advances the
        playback position. Returns fewer than `frame_count` frames to
        signal natural end-of-track.
        """
        with self._lock:
            if self._audio is None:
                return np.zeros((0, 1), dtype=np.float32)

            start = self._position_frames
            end = min(start + frame_count, self._audio.total_frames)
            chunk = self._audio.samples[start:end]

            volume = self._volume
            self._position_frames = end

        if volume != 1.0:
            chunk = chunk * np.float32(volume)
        return chunk

    def _on_output_finished(self) -> None:
        """
        Called (from a background thread owned by the audio output
        backend) once the stream has drained after `_read_frames`
        signalled end-of-data. Only fires for *natural* completion -
        `stop()` already reports `MANUAL_STOP` itself and does not
        rely on this callback.
        """
        with self._lock:
            if self._state != PlayerState.PLAYING:
                # A manual stop()/pause() beat us here; nothing to do.
                return
            self._position_frames = 0
            self._set_state(PlayerState.STOPPED)

        self._notify_track_end(TrackEndReason.COMPLETED)
