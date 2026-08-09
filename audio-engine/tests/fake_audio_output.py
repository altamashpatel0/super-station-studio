"""
fake_audio_output.py
=====================

A deterministic, hardware-free stand-in for `SoundDeviceOutput`, used
by the automated test suite. Real audio hardware is not available (or
desirable) in CI, so `Player`/`AudioEngine` are tested against this
fake, which implements the exact same `AudioOutputBase` interface.

Unlike the real backend, nothing here runs on a background thread -
tests explicitly "pump" frames to drive playback forward, which makes
end-of-track and pause/resume behaviour trivially reproducible.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_output import AudioOutputBase, ReadCallback
from src.models import AudioOutputError


class FakeAudioOutput(AudioOutputBase):
    """In-memory, synchronous fake of the real audio output device."""

    def __init__(self, fail_on_open: bool = False) -> None:
        self.fail_on_open = fail_on_open
        self.opened = False
        self.closed = False
        self.sample_rate: Optional[int] = None
        self.channels: Optional[int] = None
        self._read_callback: Optional[ReadCallback] = None
        self._on_finished: Optional[Callable[[], None]] = None
        self._active = False

    def open(self, sample_rate: int, channels: int) -> None:
        if self.fail_on_open:
            raise AudioOutputError("Simulated failure to open audio device.")
        self.sample_rate = sample_rate
        self.channels = channels
        self.opened = True

    def start(self, read_callback: ReadCallback, on_finished: Callable[[], None]) -> None:
        if not self.opened:
            raise AudioOutputError("start() called before open().")
        self._read_callback = read_callback
        self._on_finished = on_finished
        self._active = True

    def pause(self) -> None:
        self._active = False

    def resume(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def close(self) -> None:
        self.closed = True
        self._active = False
        self._read_callback = None
        self._on_finished = None

    @property
    def is_active(self) -> bool:
        return self._active

    # -- Test-driving helpers (not part of AudioOutputBase) ------------

    def pump(self, frame_count: int) -> np.ndarray:
        """Simulate the real-time thread pulling one block of frames.

        If fewer frames than requested are returned, marks the stream
        inactive and fires `on_finished`, mirroring `SoundDeviceOutput`.
        """
        assert self._read_callback is not None, "pump() called before start()"
        data = self._read_callback(frame_count)
        if len(data) < frame_count:
            self._active = False
            if self._on_finished is not None:
                self._on_finished()
        return data

    def drain(self, chunk_size: int = 1024, max_iterations: int = 100_000) -> int:
        """Pump repeatedly until the stream reports inactive (end of
        track). Returns the number of pump() calls made."""
        iterations = 0
        while self._active and iterations < max_iterations:
            self.pump(chunk_size)
            iterations += 1
        return iterations
