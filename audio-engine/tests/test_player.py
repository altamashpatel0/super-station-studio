"""Tests for `src.player.Player`."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models import (
    InvalidSeekError,
    InvalidStateError,
    InvalidVolumeError,
    PlayerState,
    TrackEndReason,
)
from src.player import Player
from tests.fake_audio_output import FakeAudioOutput


class TestInitialState:
    def test_starts_idle(self, player: Player):
        assert player.get_status().state == PlayerState.IDLE


class TestLoad:
    def test_load_valid_file_transitions_to_stopped(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        status = player.get_status()
        assert status.state == PlayerState.STOPPED
        assert status.file_path == str(valid_wav_file)
        assert status.duration_seconds > 0
        assert status.position_seconds == 0

    def test_load_missing_file_transitions_to_error(self, player: Player, missing_file_path: Path):
        with pytest.raises(Exception):
            player.load(str(missing_file_path))
        assert player.get_status().state == PlayerState.ERROR
        assert player.get_status().error_message is not None

    def test_load_corrupt_file_transitions_to_error(self, player: Player, corrupt_mp3_file: Path):
        with pytest.raises(Exception):
            player.load(str(corrupt_mp3_file))
        assert player.get_status().state == PlayerState.ERROR

    def test_load_does_not_raise_uncaught_exception_type(
        self, player: Player, corrupt_mp3_file: Path
    ):
        from src.models import AudioEngineError

        with pytest.raises(AudioEngineError):
            player.load(str(corrupt_mp3_file))

    def test_reload_after_error_recovers(
        self, player: Player, corrupt_mp3_file: Path, valid_wav_file: Path
    ):
        with pytest.raises(Exception):
            player.load(str(corrupt_mp3_file))
        assert player.get_status().state == PlayerState.ERROR

        player.load(str(valid_wav_file))
        status = player.get_status()
        assert status.state == PlayerState.STOPPED
        assert status.error_message is None


class TestPlaybackControls:
    def test_play_without_loaded_track_raises(self, player: Player):
        with pytest.raises(InvalidStateError):
            player.play()

    def test_play_transitions_to_playing(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.play()
        assert player.get_status().state == PlayerState.PLAYING

    def test_pause_while_playing_transitions_to_paused(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.play()
        player.pause()
        assert player.get_status().state == PlayerState.PAUSED

    def test_pause_while_not_playing_raises(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        with pytest.raises(InvalidStateError):
            player.pause()

    def test_resume_after_pause_transitions_to_playing(
        self, player: Player, valid_wav_file: Path
    ):
        player.load(str(valid_wav_file))
        player.play()
        player.pause()
        player.resume()
        assert player.get_status().state == PlayerState.PLAYING

    def test_resume_without_pause_raises(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.play()
        with pytest.raises(InvalidStateError):
            player.resume()

    def test_stop_while_playing_resets_position(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.play()
        player.seek(0.1)
        player.stop()
        status = player.get_status()
        assert status.state == PlayerState.STOPPED
        assert status.position_seconds == 0

    def test_stop_when_already_stopped_is_a_no_op(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.stop()  # should not raise even though nothing was playing
        assert player.get_status().state == PlayerState.STOPPED


class TestSeekValidation:
    def test_seek_without_loaded_track_raises(self, player: Player):
        with pytest.raises(InvalidStateError):
            player.seek(1.0)

    def test_seek_negative_raises(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        with pytest.raises(InvalidSeekError):
            player.seek(-1.0)

    def test_seek_beyond_duration_raises(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        status = player.get_status()
        with pytest.raises(InvalidSeekError):
            player.seek(status.duration_seconds + 10)

    def test_seek_within_range_updates_position(self, player: Player, longer_wav_file: Path):
        player.load(str(longer_wav_file))
        player.seek(1.0)
        assert player.get_status().position_seconds == pytest.approx(1.0, abs=0.05)

    def test_seek_to_zero_is_valid(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        player.seek(0.0)
        assert player.get_status().position_seconds == pytest.approx(0.0, abs=0.01)


class TestVolumeValidation:
    def test_default_volume_is_full(self, player: Player):
        assert player.get_volume() == 1.0

    def test_set_valid_volume(self, player: Player):
        player.set_volume(0.5)
        assert player.get_volume() == 0.5

    def test_set_volume_zero_is_valid(self, player: Player):
        player.set_volume(0.0)
        assert player.get_volume() == 0.0

    def test_set_volume_one_is_valid(self, player: Player):
        player.set_volume(1.0)
        assert player.get_volume() == 1.0

    def test_set_volume_above_one_raises(self, player: Player):
        with pytest.raises(InvalidVolumeError):
            player.set_volume(1.5)

    def test_set_volume_below_zero_raises(self, player: Player):
        with pytest.raises(InvalidVolumeError):
            player.set_volume(-0.1)


class TestStatusAndDuration:
    def test_status_reports_current_file(self, player: Player, valid_wav_file: Path):
        player.load(str(valid_wav_file))
        assert player.get_status().file_path == str(valid_wav_file)

    def test_status_before_load_has_no_file(self, player: Player):
        status = player.get_status()
        assert status.file_path is None
        assert status.duration_seconds == 0.0


class TestAutomaticEndDetection:
    def test_track_completion_transitions_to_stopped_and_fires_event(
        self, player: Player, valid_wav_file: Path, fake_output: FakeAudioOutput
    ):
        received_reasons = []
        player.on_track_end(received_reasons.append)

        player.load(str(valid_wav_file))
        player.play()
        fake_output.drain(chunk_size=512)

        status = player.get_status()
        assert status.state == PlayerState.STOPPED
        assert status.position_seconds == 0
        assert received_reasons == [TrackEndReason.COMPLETED]

    def test_manual_stop_fires_manual_stop_reason(
        self, player: Player, valid_wav_file: Path
    ):
        received_reasons = []
        player.on_track_end(received_reasons.append)

        player.load(str(valid_wav_file))
        player.play()
        player.stop()

        assert received_reasons == [TrackEndReason.MANUAL_STOP]

    def test_state_change_listener_receives_transitions(
        self, player: Player, valid_wav_file: Path
    ):
        transitions = []
        player.on_state_change(lambda old, new: transitions.append((old, new)))

        player.load(str(valid_wav_file))
        player.play()
        player.stop()

        assert (PlayerState.IDLE, PlayerState.LOADING) in transitions
        assert (PlayerState.LOADING, PlayerState.STOPPED) in transitions
        assert (PlayerState.STOPPED, PlayerState.PLAYING) in transitions
        assert (PlayerState.PLAYING, PlayerState.STOPPED) in transitions


class TestOutputFailureNeverCrashes:
    def test_play_with_output_open_failure_transitions_to_error(
        self, valid_wav_file: Path
    ):
        failing_output = FakeAudioOutput(fail_on_open=True)
        player = Player(audio_output=failing_output)
        player.load(str(valid_wav_file))

        with pytest.raises(Exception):
            player.play()

        assert player.get_status().state == PlayerState.ERROR
