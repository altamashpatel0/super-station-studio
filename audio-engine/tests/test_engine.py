"""Tests for `src.engine.AudioEngine` - the future FastAPI-facing API."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engine import AudioEngine
from src.models import AudioEngineError, PlayerState
from tests.fake_audio_output import FakeAudioOutput


def test_full_playback_lifecycle(engine: AudioEngine, valid_wav_file: Path):
    status = engine.load_track(str(valid_wav_file))
    assert status.state == PlayerState.STOPPED

    status = engine.play()
    assert status.state == PlayerState.PLAYING
    assert engine.is_playing() is True

    status = engine.pause()
    assert status.state == PlayerState.PAUSED
    assert engine.is_playing() is False

    status = engine.resume()
    assert status.state == PlayerState.PLAYING

    status = engine.stop()
    assert status.state == PlayerState.STOPPED
    assert status.position_seconds == 0


def test_load_invalid_file_raises_audio_engine_error(
    engine: AudioEngine, corrupt_mp3_file: Path
):
    with pytest.raises(AudioEngineError):
        engine.load_track(str(corrupt_mp3_file))
    assert engine.get_state() == PlayerState.ERROR


def test_load_missing_file_raises_audio_engine_error(
    engine: AudioEngine, missing_file_path: Path
):
    with pytest.raises(AudioEngineError):
        engine.load_track(str(missing_file_path))
    assert engine.get_state() == PlayerState.ERROR


def test_seek_and_volume_round_trip(engine: AudioEngine, longer_wav_file: Path):
    engine.load_track(str(longer_wav_file))
    engine.seek(1.0)
    status = engine.get_status()
    assert status.position_seconds == pytest.approx(1.0, abs=0.05)

    engine.set_volume(0.25)
    assert engine.get_volume() == 0.25


def test_status_serializes_to_plain_dict(engine: AudioEngine, valid_wav_file: Path):
    engine.load_track(str(valid_wav_file))
    payload = engine.get_status().to_dict()

    assert payload["state"] == "STOPPED"
    assert payload["file_path"] == str(valid_wav_file)
    assert isinstance(payload["duration_seconds"], float)


def test_on_track_complete_fires_for_natural_completion(
    engine: AudioEngine, valid_wav_file: Path, fake_output: FakeAudioOutput
):
    completed_files = []
    engine.on_track_complete(completed_files.append)

    engine.load_track(str(valid_wav_file))
    engine.play()
    fake_output.drain(chunk_size=256)

    assert completed_files == [str(valid_wav_file)]


def test_on_track_complete_does_not_fire_for_manual_stop(
    engine: AudioEngine, valid_wav_file: Path
):
    completed_files = []
    engine.on_track_complete(completed_files.append)

    engine.load_track(str(valid_wav_file))
    engine.play()
    engine.stop()

    assert completed_files == []


def test_context_manager_shuts_down_cleanly(fake_output: FakeAudioOutput, valid_wav_file: Path):
    with AudioEngine(audio_output=fake_output) as engine:
        engine.load_track(str(valid_wav_file))
        engine.play()

    assert fake_output.closed is True
