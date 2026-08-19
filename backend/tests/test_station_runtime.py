from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.services.station_runtime import StationRuntime


def test_rejects_non_positive_health_interval():
    runtime = MagicMock()

    with pytest.raises(ValueError):
        StationRuntime(runtime, health_interval_seconds=0)

    with pytest.raises(ValueError):
        StationRuntime(runtime, health_interval_seconds=-1)


def test_start_is_idempotent():
    runtime = MagicMock()
    worker = MagicMock()
    worker.start.return_value = True
    continuation = MagicMock()
    watchdog = MagicMock()
    watchdog.start.return_value = True
    recovery = MagicMock()

    station = StationRuntime(
        runtime,
        recovery=recovery,
        worker=worker,
        continuation=continuation,
        watchdog=watchdog,
        health_interval_seconds=0.01,
    )

    assert station.start() is True
    assert station.start() is False

    station.stop()

    continuation.attach.assert_called_once_with()
    watchdog.start.assert_called_once_with()
    worker.start.assert_called_once_with()


def test_stop_is_safe_before_start():
    runtime = MagicMock()
    station = StationRuntime(
        runtime,
        worker=MagicMock(),
        continuation=MagicMock(),
        watchdog=MagicMock(),
    )

    assert station.stop() is False


def test_stop_order_is_worker_watchdog_health_then_continuation():
    runtime = MagicMock()
    events = []

    worker = MagicMock()
    worker.stop.side_effect = lambda timeout=2.0: events.append("worker")
    watchdog = MagicMock()
    watchdog.stop.side_effect = lambda timeout=2.0: events.append("watchdog")
    continuation = MagicMock()
    continuation.detach.side_effect = lambda: events.append("continuation")

    station = StationRuntime(
        runtime,
        worker=worker,
        continuation=continuation,
        watchdog=watchdog,
        health_interval_seconds=0.01,
    )

    station.start()
    station.stop()

    assert events[:3] == ["worker", "watchdog", "continuation"]


def test_stalled_recovery_rearms_runtime_and_resets_retry_budget():
    runtime = MagicMock()
    recovery = MagicMock()
    station = StationRuntime(
        runtime,
        recovery=recovery,
        worker=MagicMock(),
        continuation=MagicMock(),
        watchdog=MagicMock(),
    )

    station._recover_stalled_playback()

    runtime.reset_occurrence.assert_called_once_with()
    recovery.reset.assert_called_once_with()


def test_context_manager_starts_and_stops():
    runtime = MagicMock()
    worker = MagicMock()
    watchdog = MagicMock()
    continuation = MagicMock()

    station = StationRuntime(
        runtime,
        worker=worker,
        watchdog=watchdog,
        continuation=continuation,
        health_interval_seconds=0.01,
    )

    with station:
        assert station.is_running is True

    assert station.is_running is False
    worker.start.assert_called_once_with()
    worker.stop.assert_called_once()
    watchdog.start.assert_called_once_with()
    watchdog.stop.assert_called_once()
    continuation.attach.assert_called_once_with()
    continuation.detach.assert_called_once_with()


def test_start_failure_rolls_back_lifecycle():
    runtime = MagicMock()
    continuation = MagicMock()
    continuation.attach.side_effect = RuntimeError("attach failed")
    watchdog = MagicMock()
    worker = MagicMock()

    station = StationRuntime(
        runtime,
        worker=worker,
        watchdog=watchdog,
        continuation=continuation,
    )

    with pytest.raises(RuntimeError, match="attach failed"):
        station.start()

    assert station.is_running is False
    worker.stop.assert_called_once()
    watchdog.stop.assert_called_once()


def test_health_bridge_marks_advancing_playback_healthy():
    runtime = MagicMock()
    status1 = MagicMock()
    status2 = MagicMock()
    status1.state = __import__("src.models", fromlist=["PlayerState"]).PlayerState.PLAYING
    status2.state = status1.state
    status1.position_seconds = 1.0
    status2.position_seconds = 2.0
    status1.file_path = "song.mp3"
    status2.file_path = "song.mp3"
    runtime.engine.get_status.side_effect = [status1, status2]

    watchdog = MagicMock()
    station = StationRuntime(
        runtime,
        worker=MagicMock(),
        continuation=MagicMock(),
        watchdog=watchdog,
        health_interval_seconds=1,
    )

    station._sample_playback()
    station._sample_playback()

    assert watchdog.notify_playback_started.called
    assert watchdog.heartbeat.called


def test_health_bridge_marks_non_playing_idle():
    runtime = MagicMock()
    status = MagicMock()
    status.state = __import__("src.models", fromlist=["PlayerState"]).PlayerState.STOPPED
    status.file_path = None
    status.position_seconds = 0.0
    runtime.engine.get_status.return_value = status

    watchdog = MagicMock()
    station = StationRuntime(
        runtime,
        worker=MagicMock(),
        continuation=MagicMock(),
        watchdog=watchdog,
    )

    station._sample_playback()

    watchdog.notify_playback_stopped.assert_called_once_with()
