from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from app.services.automation_worker import AutomationWorker


def _worker(*, interval=0.01):
    runtime = MagicMock()
    runtime.tick.return_value = None

    worker = AutomationWorker(
        runtime,
        interval_seconds=interval,
    )
    return worker, runtime


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_rejects_non_positive_interval():
    runtime = MagicMock()

    with pytest.raises(ValueError, match="greater than zero"):
        AutomationWorker(runtime, interval_seconds=0)

    with pytest.raises(ValueError, match="greater than zero"):
        AutomationWorker(runtime, interval_seconds=-1)


def test_start_is_idempotent():
    worker, runtime = _worker()

    assert worker.start() is True
    assert worker.start() is False

    assert _wait_until(lambda: runtime.tick.call_count >= 1)

    worker.stop()

    assert worker.is_running is False


def test_worker_calls_scheduler_runtime_continuously():
    worker, runtime = _worker(interval=0.01)

    worker.start()

    assert _wait_until(lambda: runtime.tick.call_count >= 3)

    worker.stop()

    assert runtime.tick.call_count >= 3
    assert worker.tick_count >= 3
    assert worker.is_running is False


def test_stop_before_start_is_safe():
    worker, runtime = _worker()

    assert worker.stop() is False
    assert worker.is_running is False
    runtime.tick.assert_not_called()


def test_stop_stops_background_loop():
    worker, runtime = _worker(interval=0.01)

    worker.start()
    assert _wait_until(lambda: runtime.tick.call_count >= 1)

    worker.stop()
    calls_after_stop = runtime.tick.call_count

    time.sleep(0.05)

    assert runtime.tick.call_count == calls_after_stop
    assert worker.is_running is False


def test_run_once_calls_runtime_and_counts_tick():
    worker, runtime = _worker()

    result = worker.run_once()

    assert result is None
    runtime.tick.assert_called_once_with()
    assert worker.tick_count == 1
    assert worker.last_error is None


def test_run_once_returns_runtime_result():
    worker, runtime = _worker()
    expected = object()
    runtime.tick.return_value = expected

    assert worker.run_once() is expected
    assert worker.tick_count == 1


def test_runtime_error_is_recorded_and_re_raised_for_run_once():
    worker, runtime = _worker()
    runtime.tick.side_effect = RuntimeError("temporary scheduler failure")

    with pytest.raises(RuntimeError, match="temporary scheduler failure"):
        worker.run_once()

    assert worker.last_error == "temporary scheduler failure"
    assert worker.tick_count == 0


def test_background_error_does_not_kill_worker():
    worker, runtime = _worker(interval=0.01)

    calls = {"count": 0}

    def tick():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")
        return None

    runtime.tick.side_effect = tick

    worker.start()

    assert _wait_until(lambda: runtime.tick.call_count >= 3)

    worker.stop()

    assert runtime.tick.call_count >= 3
    assert worker.tick_count >= 2
    assert worker.last_error is None


def test_shutdown_is_alias_for_stop():
    worker, runtime = _worker(interval=0.01)

    worker.start()
    assert _wait_until(lambda: runtime.tick.call_count >= 1)

    assert worker.shutdown() is True
    assert worker.is_running is False


def test_context_manager_starts_and_stops_worker():
    worker, runtime = _worker(interval=0.01)

    with worker:
        assert _wait_until(lambda: runtime.tick.call_count >= 1)
        assert worker.is_running is True

    assert worker.is_running is False


def test_worker_does_not_call_runtime_start_or_stop():
    worker, runtime = _worker(interval=0.01)

    worker.start()
    assert _wait_until(lambda: runtime.tick.call_count >= 1)
    worker.stop()

    runtime.start.assert_not_called()
    runtime.stop.assert_not_called()


def test_multiple_workers_can_be_constructed_without_global_state():
    runtime_a = MagicMock()
    runtime_b = MagicMock()

    worker_a = AutomationWorker(runtime_a, interval_seconds=0.01)
    worker_b = AutomationWorker(runtime_b, interval_seconds=0.01)

    assert worker_a.start() is True
    assert worker_b.start() is True

    assert _wait_until(lambda: runtime_a.tick.call_count >= 1)
    assert _wait_until(lambda: runtime_b.tick.call_count >= 1)

    worker_a.stop()
    worker_b.stop()

    assert worker_a.is_running is False
    assert worker_b.is_running is False
