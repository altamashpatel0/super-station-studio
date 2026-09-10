"""
decoder.py
==========

Responsible for everything related to turning a file on disk into raw
PCM audio data plus its metadata (sample rate, channels, duration).

This module knows nothing about playback state, threads, or audio
devices - it is a pure "file in, samples out" component, which makes
it easy to unit test in isolation and easy to swap the underlying
decoding library later without touching `player.py` or `engine.py`.

Decoding backend: PyAV (bundles FFmpeg), which gives us robust MP3/WAV
support today and headroom for AAC/FLAC/OGG/etc. later without adding
new dependencies.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import av
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "PyAV is required for audio decoding. Install it with "
        "`pip install av` (see requirements.txt)."
    ) from exc

from .models import (
    AudioFileNotFoundError,
    DecodeError,
    UnsupportedFormatError,
)

logger = logging.getLogger(__name__)

# Extensions the engine advertises as supported in V0.1. PyAV/FFmpeg can
# technically decode more, but we deliberately restrict the surface area
# to what has been validated for this release.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav"})

# Internal PCM representation used throughout the engine.
TARGET_SAMPLE_FORMAT = "fltp"  # planar float32, resampled to interleaved below
OUTPUT_DTYPE = np.float32


@dataclass(frozen=True)
class DecodedAudio:
    """
    Fully decoded audio, ready to be handed to the audio output layer.

    `samples` is an interleaved float32 numpy array of shape
    (num_frames, num_channels) with values nominally in [-1.0, 1.0].
    """

    file_path: str
    samples: np.ndarray
    sample_rate: int
    channels: int

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return len(self.samples) / float(self.sample_rate)

    @property
    def total_frames(self) -> int:
        return len(self.samples)


class AudioDecoder:
    """Validates and decodes local audio files into `DecodedAudio`.

    The decoder keeps a single optional *next-track* cache. Queue playback
    can ask for the following song while the current song is still playing,
    so the potentially expensive PyAV decode happens off the audio/end-event
    path. Keeping only one decoded track bounds memory usage on low-end PCs.
    """

    def __init__(self) -> None:
        self._cache_lock = threading.RLock()
        self._cached_audio: DecodedAudio | None = None
        self._preloading_path: str | None = None

    def preload(self, file_path: str) -> None:
        """Decode one future track in the background and cache it.

        This method is best-effort: preload failures are logged and never
        affect the currently playing track. Only one track is retained.
        """
        if not file_path:
            return
        with self._cache_lock:
            if self._cached_audio is not None and self._cached_audio.file_path == file_path:
                return
            if self._preloading_path == file_path:
                return
            self._preloading_path = file_path

        def worker() -> None:
            try:
                decoded = self.decode(file_path, use_cache=False)
                with self._cache_lock:
                    self._cached_audio = decoded
            except Exception:
                logger.debug("Background preload failed for '%s'.", file_path, exc_info=True)
            finally:
                with self._cache_lock:
                    if self._preloading_path == file_path:
                        self._preloading_path = None

        threading.Thread(
            target=worker,
            name="AudioDecoderPreload",
            daemon=True,
        ).start()

    @staticmethod
    def supported_extensions() -> Iterable[str]:
        """Return the set of file extensions this decoder accepts."""
        return SUPPORTED_EXTENSIONS

    @staticmethod
    def validate_file(file_path: str) -> None:
        """
        Validate that a path points to an existing, supported audio file.

        Raises:
            AudioFileNotFoundError: if the path does not exist or is not
                a regular file.
            UnsupportedFormatError: if the file extension is not one of
                the formats this decoder supports.
        """
        if not file_path:
            raise AudioFileNotFoundError("No file path was provided.")

        path = Path(file_path)

        if not path.exists() or not path.is_file():
            raise AudioFileNotFoundError(f"Audio file not found: {file_path}")

        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise UnsupportedFormatError(
                f"Unsupported audio format '{extension}' for file "
                f"'{file_path}'. Supported formats: {supported}"
            )

    def decode(self, file_path: str, *, use_cache: bool = True) -> DecodedAudio:
        """
        Decode an audio file fully into memory.

        Full in-memory decoding (rather than streaming) is a deliberate
        choice for V0.1: radio automation tracks are short (seconds to
        a few minutes), and having the entire track in memory makes
        sample-accurate seeking, looping, and future crossfading trivial
        to implement reliably.

        Raises:
            AudioFileNotFoundError: file missing (see `validate_file`).
            UnsupportedFormatError: extension not supported.
            DecodeError: the file matched a supported extension but
                could not actually be decoded (corrupt/invalid data).
        """
        self.validate_file(file_path)

        if use_cache:
            with self._cache_lock:
                cached = self._cached_audio
                if cached is not None and cached.file_path == file_path:
                    self._cached_audio = None
                    return cached

        try:
            container = av.open(file_path)
        except av.error.FFmpegError as exc:  # broad PyAV decode/open failure
            raise DecodeError(
                f"Failed to open '{file_path}' for decoding: {exc}"
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive catch-all
            raise DecodeError(
                f"Unexpected error opening '{file_path}': {exc}"
            ) from exc

        try:
            audio_streams = [s for s in container.streams if s.type == "audio"]
            if not audio_streams:
                raise DecodeError(
                    f"'{file_path}' does not contain an audio stream."
                )
            stream = audio_streams[0]

            channels = stream.codec_context.channels or 1
            sample_rate = stream.codec_context.sample_rate or 44100

            resampler = av.AudioResampler(
                format=TARGET_SAMPLE_FORMAT,
                layout="stereo" if channels > 1 else "mono",
                rate=sample_rate,
            )

            chunks: list[np.ndarray] = []
            for frame in container.decode(stream):
                try:
                    resampled_frames = resampler.resample(frame)
                except Exception as exc:
                    raise DecodeError(
                        f"Error decoding audio data in '{file_path}': {exc}"
                    ) from exc

                for resampled in resampled_frames:
                    array = resampled.to_ndarray()  # shape: (channels, samples)
                    chunks.append(array)

            if not chunks:
                raise DecodeError(
                    f"'{file_path}' produced no decodable audio frames "
                    "(file may be empty or corrupt)."
                )

            planar = np.concatenate(chunks, axis=1)  # (channels, total_samples)
            interleaved = np.ascontiguousarray(planar.T).astype(OUTPUT_DTYPE)

            if interleaved.size == 0:
                raise DecodeError(f"'{file_path}' decoded to zero audio frames.")

            actual_channels = interleaved.shape[1]

            logger.info(
                "Decoded '%s': %d frames, %d Hz, %d channel(s), %.2fs",
                file_path,
                interleaved.shape[0],
                sample_rate,
                actual_channels,
                interleaved.shape[0] / float(sample_rate),
            )

            return DecodedAudio(
                file_path=file_path,
                samples=interleaved,
                sample_rate=sample_rate,
                channels=actual_channels,
            )
        except DecodeError:
            raise
        except Exception as exc:
            raise DecodeError(
                f"Unexpected error decoding '{file_path}': {exc}"
            ) from exc
        finally:
            container.close()
