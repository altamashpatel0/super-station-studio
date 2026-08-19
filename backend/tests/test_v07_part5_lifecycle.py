from __future__ import annotations

from unittest.mock import MagicMock

from app.services.station_runtime import StationRuntime


def test_single_station_instance_can_be_started_and_stopped_repeatedly():
    runtime = MagicMock()
    worker = MagicMock()
    watchdog = MagicMock()
    continuation = MagicMock()

    station = StationRuntime(
        runtime,
        worker=worker,
        watchdog=watchdog,
        continuation=continuation,
    )

    assert station.start() is True
    assert station.stop() is True
    assert station.start() is True
    assert station.stop() is True

    assert worker.start.call_count == 2
    assert worker.stop.call_count == 2
    assert watchdog.start.call_count == 2
    assert watchdog.stop.call_count == 2
    assert continuation.attach.call_count == 2
    assert continuation.detach.call_count == 2
