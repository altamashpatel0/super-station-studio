"""
conftest.py
===========

Shared pytest fixtures:
  - Real, valid, tiny WAV files generated on the fly (no binary test
    assets committed to the repo).
  - A deliberately corrupt "audio" file to exercise decode failures.
  - A pre-wired `AudioEngine`/`Player` using `FakeAudioOutput` so tests
    never touch real audio hardware.
"""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.decoder import AudioDecoder
from src.engine import AudioEngine
from src.player import Player
from tests.fake_audio_output import FakeAudioOutput


def _write_wav(path: Path, duration_seconds: float, sample_rate: int = 8000) -> Path:
    """Write a tiny, valid, silent mono 16-bit PCM WAV file."""
    n_frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        silence_frame = struct.pack("<h", 0)
        wav_file.writeframes(silence_frame * n_frames)
    return path


@pytest.fixture
def valid_wav_file(tmp_path: Path) -> Path:
    """A short (0.5s), valid, decodable WAV file."""
    return _write_wav(tmp_path / "valid_tone.wav", duration_seconds=0.5)


@pytest.fixture
def longer_wav_file(tmp_path: Path) -> Path:
    """A slightly longer (2s) valid WAV file, useful for seek tests."""
    return _write_wav(tmp_path / "longer_tone.wav", duration_seconds=2.0)


def _write_mp3(path: Path, duration_seconds: float = 0.5, sample_rate: int = 44100) -> Path:
    """Encode a tiny, real, valid MP3 file (a quiet sine tone) using
    PyAV, so decode tests exercise the actual MP3 codec path rather
    than only WAV."""
    import av

    container = av.open(str(path), mode="w")
    stream = container.add_stream("mp3", rate=sample_rate)
    stream.channels = 2

    n_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, n_samples, endpoint=False)
    tone = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    stereo = np.stack([tone, tone])

    frame = av.AudioFrame.from_ndarray(stereo, format="fltp", layout="stereo")
    frame.sample_rate = sample_rate

    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()
    return path


@pytest.fixture
def valid_mp3_file(tmp_path: Path) -> Path:
    """A short (0.5s), valid, decodable, real MP3 file."""
    return _write_mp3(tmp_path / "valid_tone.mp3", duration_seconds=0.5)


@pytest.fixture
def corrupt_mp3_file(tmp_path: Path) -> Path:
    """A file with an .mp3 extension but garbage content."""
    path = tmp_path / "corrupt.mp3"
    path.write_bytes(b"this is not a real mp3 file" * 20)
    return path


@pytest.fixture
def missing_file_path(tmp_path: Path) -> Path:
    """A syntactically valid path that does not exist on disk."""
    return tmp_path / "does_not_exist.mp3"


@pytest.fixture
def unsupported_format_file(tmp_path: Path) -> Path:
    """A file with an unsupported extension."""
    path = tmp_path / "notes.txt"
    path.write_text("not audio")
    return path


@pytest.fixture
def decoder() -> AudioDecoder:
    return AudioDecoder()


@pytest.fixture
def fake_output() -> FakeAudioOutput:
    return FakeAudioOutput()


@pytest.fixture
def player(fake_output: FakeAudioOutput) -> Player:
    return Player(audio_output=fake_output)


@pytest.fixture
def engine(fake_output: FakeAudioOutput) -> AudioEngine:
    return AudioEngine(audio_output=fake_output)
