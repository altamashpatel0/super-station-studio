from __future__ import annotations

from unittest.mock import MagicMock

from app.services.playback_continuation import PlaybackContinuation


class FakeReason:
    COMPLETED = "COMPLETED"
    MANUAL_STOP = "MANUAL_STOP"
    ERROR = "ERROR"


def _continuation():
    runtime = MagicMock()
    runtime.engine.on_track_end = MagicMock()
    return PlaybackContinuation(runtime), runtime


def test_attach_registers_once():
    continuation, runtime = _continuation()

    continuation.attach()
    continuation.attach()

    runtime.engine.on_track_end.assert_called_once()
    assert continuation.running is True


def test_completed_resets_scheduler_occurrence():
    continuation, runtime = _continuation()

    continuation.attach()
    callback = runtime.engine.on_track_end.call_args.args[0]

    callback(FakeReason.COMPLETED)

    runtime.reset_occurrence.assert_called_once_with()
    assert continuation.last_reason == FakeReason.COMPLETED


def test_manual_stop_does_not_continue():
    continuation, runtime = _continuation()

    continuation.attach()
    callback = runtime.engine.on_track_end.call_args.args[0]

    callback(FakeReason.MANUAL_STOP)

    runtime.reset_occurrence.assert_not_called()
    assert continuation.last_reason == FakeReason.MANUAL_STOP


def test_error_does_not_continue():
    continuation, runtime = _continuation()

    continuation.attach()
    callback = runtime.engine.on_track_end.call_args.args[0]

    callback(FakeReason.ERROR)

    runtime.reset_occurrence.assert_not_called()
    assert continuation.last_reason == FakeReason.ERROR


def test_detached_callback_is_ignored():
    continuation, runtime = _continuation()

    continuation.attach()
    callback = runtime.engine.on_track_end.call_args.args[0]
    continuation.detach()

    callback(FakeReason.COMPLETED)

    runtime.reset_occurrence.assert_not_called()
    assert continuation.running is False


def test_shutdown_detaches():
    continuation, runtime = _continuation()

    continuation.attach()
    continuation.shutdown()

    callback = runtime.engine.on_track_end.call_args.args[0]
    callback(FakeReason.COMPLETED)

    runtime.reset_occurrence.assert_not_called()
    assert continuation.running is False


def test_context_manager_attaches_and_detaches():
    continuation, runtime = _continuation()

    with continuation:
        assert continuation.running is True

    assert continuation.running is False


def test_completion_callback_does_not_play_audio_directly():
    continuation, runtime = _continuation()

    continuation.attach()
    callback = runtime.engine.on_track_end.call_args.args[0]
    callback(FakeReason.COMPLETED)

    runtime.engine.load_track.assert_not_called()
    runtime.engine.play.assert_not_called()
    runtime.asset_playback_manager.play_asset.assert_not_called()
