"""
tests/fakes.py
================

Fakes for the V0.1 `AudioDecoder` / `AudioOutputBase` seams, so V0.3
integration tests can drive the *real, unmodified* `AudioEngine` /
`Player` state machine deterministically, without real audio hardware
(`sounddevice`) or real MP3/WAV decoding (`PyAV`).

Nothing about `AudioEngine`, `Player`, or the queue integration code
is mocked - only the two abstract seams V0.1 already designed for this
purpose (`decoder: Optional[AudioDecoder]`, `audio_output:
Optional[AudioOutputBase]` on `Player.__init__` / `AudioEngine.__init__`).
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from src.decoder import AudioDecoder, DecodedAudio
from src.audio_output import AudioOutputBase
from src.models import DecodeError


class FakeDecoder(AudioDecoder):
    """
    Decodes only paths explicitly `register()`-ed by a test, with a
    tiny synthetic PCM buffer instead of real audio data.

    `validate_file()` (existence + supported extension) is inherited
    unmodified from the real `AudioDecoder` - so "file doesn't exist on
    disk" is exercised exactly as it would be in production. Only the
    actual decode step is faked, and only for registered paths;
    unregistered-but-existing paths raise `DecodeError`, simulating a
    corrupt/unreadable file.
    """

    def __init__(self) -> None:
        self._registry: dict[str, DecodedAudio] = {}

    def register(
        self,
        file_path: str,
        *,
        duration_seconds: float = 0.05,
        sample_rate: int = 8000,
        channels: int = 1,
    ) -> None:
        n_frames = max(1, int(duration_seconds * sample_rate))
        samples = np.zeros((n_frames, channels), dtype=np.float32)
        self._registry[file_path] = DecodedAudio(
            file_path=file_path,
            samples=samples,
            sample_rate=sample_rate,
            channels=channels,
        )

    def decode(self, file_path: str) -> DecodedAudio:  # type: ignore[override]
        self.validate_file(file_path)
        decoded = self._registry.get(file_path)
        if decoded is None:
            raise DecodeError(
                f"'{file_path}' is not a registered fake track "
                "(simulates a corrupt/unsupported file in tests)."
            )
        return decoded


class FakeAudioOutput(AudioOutputBase):
    """
    Synchronous, single-threaded fake of `AudioOutputBase`.

    Real playback happens on a background real-time audio thread and
    drains asynchronously; that's exactly what makes natural-completion
    timing non-deterministic to test against. This fake instead hands
    control to the test: `start()` just records the callbacks, and
    nothing plays until the test calls `simulate_completion()`, which
    synchronously drains `read_callback` (mirroring what
    `SoundDeviceOutput` does for real audio) and then fires
    `on_finished()` - triggering the real `Player`/`AudioEngine`
    COMPLETED path with no timing flakiness.
    """

    def __init__(self) -> None:
        self._read_callback: Optional[Callable[[int], np.ndarray]] = None
        self._on_finished: Optional[Callable[[], None]] = None
        self._opened = False
        self._active = False

    def open(self, sample_rate: int, channels: int) -> None:
        self._opened = True

    def start(self, read_callback: Callable[[int], np.ndarray], on_finished: Callable[[], None]) -> None:
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
        self._opened = False
        self._read_callback = None
        self._on_finished = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # Test control
    # ------------------------------------------------------------------

    def simulate_completion(self, chunk_size: int = 4096) -> None:
        """Drain the currently-loaded track to natural end-of-data and
        fire the engine's COMPLETED path, synchronously."""
        if self._read_callback is None or self._on_finished is None:
            return
        while True:
            data = self._read_callback(chunk_size)
            n = 0 if data is None else len(data)
            if n < chunk_size:
                break
        self._active = False
        self._on_finished()
