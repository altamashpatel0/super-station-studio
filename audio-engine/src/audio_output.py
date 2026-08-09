"""
audio_output.py
================

Handles the audio *output device* only: opening a stream at a given
sample rate/channel count, pulling PCM frames from the player via a
callback, and pushing them to the Windows audio device.

`player.py` never talks to `sounddevice` directly - it only depends on
`AudioOutputBase`, so the actual output backend can be swapped (or
mocked in tests) without touching player logic.

Backend: `sounddevice` (PortAudio bindings). PortAudio has solid,
long-standing WASAPI/DirectSound support on Windows, which makes it a
reasonable default for a professional playout engine. `pygame` is
explicitly not used, per project requirements.
"""

from __future__ import annotations

import abc
import logging
import threading
from typing import Callable, Optional

import numpy as np

from .models import AudioOutputError

logger = logging.getLogger(__name__)

# A read callback: given a requested frame count, return up to that many
# interleaved float32 frames of shape (n_frames <= requested, channels).
# Returning fewer frames than requested signals "end of stream".
ReadCallback = Callable[[int], np.ndarray]


class AudioOutputBase(abc.ABC):
    """Abstract interface for a streaming PCM audio output device."""

    @abc.abstractmethod
    def open(self, sample_rate: int, channels: int) -> None:
        """Open the output device for the given format. Does not start
        audio flowing yet."""

    @abc.abstractmethod
    def start(self, read_callback: ReadCallback, on_finished: Callable[[], None]) -> None:
        """
        Begin pulling audio from `read_callback` and playing it.

        `on_finished` is invoked (from a background thread) once the
        stream has consumed a short final chunk, i.e. natural end of
        data as signalled by `read_callback` returning fewer frames
        than requested.
        """

    @abc.abstractmethod
    def pause(self) -> None:
        """Temporarily halt callback invocation without closing the
        device, so playback can resume from the same position."""

    @abc.abstractmethod
    def resume(self) -> None:
        """Resume a paused stream."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop and close the underlying stream (but keep the device
        object reusable via `open`/`start` again)."""

    @abc.abstractmethod
    def close(self) -> None:
        """Fully release the output device."""

    @property
    @abc.abstractmethod
    def is_active(self) -> bool:
        """Whether audio is currently flowing (started and not paused)."""


class SoundDeviceOutput(AudioOutputBase):
    """`sounddevice`-backed implementation of `AudioOutputBase`."""

    def __init__(self) -> None:
        self._stream = None
        self._sample_rate: Optional[int] = None
        self._channels: Optional[int] = None
        self._read_callback: Optional[ReadCallback] = None
        self._on_finished: Optional[Callable[[], None]] = None
        self._active = False
        self._lock = threading.Lock()

    def open(self, sample_rate: int, channels: int) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - import guard
            raise AudioOutputError(
                "The 'sounddevice' package is required for audio output. "
                "Install it with `pip install sounddevice`."
            ) from exc

        self._sample_rate = sample_rate
        self._channels = channels

        try:
            self._stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                callback=self._stream_callback,
                finished_callback=self._stream_finished,
            )
        except Exception as exc:
            raise AudioOutputError(
                f"Failed to open audio output device "
                f"({sample_rate} Hz, {channels} ch): {exc}"
            ) from exc

    def _stream_callback(self, outdata, frames, time_info, status) -> None:  # noqa: D401
        import sounddevice as sd  # local import: avoids hard dependency at module load

        if status:
            logger.warning("Audio output stream status: %s", status)

        if self._read_callback is None:
            outdata[:] = 0
            return

        try:
            data = self._read_callback(frames)
        except Exception:
            logger.exception("Error pulling audio frames from player callback")
            outdata[:] = 0
            raise sd.CallbackAbort

        n = 0 if data is None else len(data)
        if n >= frames:
            outdata[:] = data[:frames]
        else:
            outdata[:n] = data
            outdata[n:] = 0
            with self._lock:
                self._active = False
            raise sd.CallbackStop

    def _stream_finished(self) -> None:
        with self._lock:
            self._active = False
        if self._on_finished is not None:
            try:
                self._on_finished()
            except Exception:  # pragma: no cover - defensive
                logger.exception("on_finished callback raised an exception")

    def start(self, read_callback: ReadCallback, on_finished: Callable[[], None]) -> None:
        if self._stream is None:
            raise AudioOutputError("start() called before open().")

        self._read_callback = read_callback
        self._on_finished = on_finished

        try:
            self._stream.start()
            with self._lock:
                self._active = True
        except Exception as exc:
            raise AudioOutputError(f"Failed to start audio output stream: {exc}") from exc

    def pause(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            with self._lock:
                self._active = False
        except Exception as exc:
            raise AudioOutputError(f"Failed to pause audio output stream: {exc}") from exc

    def resume(self) -> None:
        if self._stream is None:
            raise AudioOutputError("resume() called before open().")
        try:
            self._stream.start()
            with self._lock:
                self._active = True
        except Exception as exc:
            raise AudioOutputError(f"Failed to resume audio output stream: {exc}") from exc

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop(ignore_errors=True)
        except Exception:  # pragma: no cover - best-effort teardown
            logger.exception("Error stopping audio output stream")
        with self._lock:
            self._active = False

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.close(ignore_errors=True)
        except Exception:  # pragma: no cover - best-effort teardown
            logger.exception("Error closing audio output stream")
        finally:
            self._stream = None
            self._read_callback = None
            self._on_finished = None
            with self._lock:
                self._active = False

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active
