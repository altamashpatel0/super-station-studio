from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.scheduler_recovery import SchedulerFailureRecovery
from app.services.scheduler_runtime import SchedulerRuntimeError


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def _recovery(*, max_retries=3, delay=1.0):
    runtime = MagicMock()
    clock = FakeClock()
    recovery = SchedulerFailureRecovery(
        runtime,
        max_retries=max_retries,
        retry_delay_seconds=delay,
        clock=clock,
    )
    return recovery, runtime, clock


def test_rejects_invalid_configuration():
    runtime = MagicMock()

    with pytest.raises(ValueError):
        SchedulerFailureRecovery(runtime, max_retries=0)

    with pytest.raises(ValueError):
        SchedulerFailureRecovery(runtime, retry_delay_seconds=-1)


def test_success_clears_previous_failure_state():
    recovery, runtime, clock = _recovery()
    runtime.tick.return_value = "ok"

    assert recovery.execute() == "ok"
    assert recovery.failure_count == 0
    assert recovery.last_error is None
    assert recovery.suppressed is False


def test_failure_is_bounded_and_does_not_raise():
    recovery, runtime, clock = _recovery(max_retries=3, delay=0)
    runtime.tick.side_effect = SchedulerRuntimeError("bad target")

    assert recovery.execute() is None
    assert recovery.failure_count == 1

    assert recovery.execute() is None
    assert recovery.failure_count == 2

    assert recovery.execute() is None
    assert recovery.failure_count == 3
    runtime.suppress_current_occurrence.assert_called_once_with()
    assert recovery.suppressed is True


def test_retry_backoff_prevents_tight_loop():
    recovery, runtime, clock = _recovery(max_retries=3, delay=2)
    runtime.tick.side_effect = SchedulerRuntimeError("temporary")

    recovery.execute()
    assert runtime.tick.call_count == 1

    recovery.execute()
    assert runtime.tick.call_count == 1

    clock.advance(2)
    recovery.execute()
    assert runtime.tick.call_count == 2


def test_success_after_failure_resets_budget():
    recovery, runtime, clock = _recovery(max_retries=3, delay=0)
    runtime.tick.side_effect = [
        SchedulerRuntimeError("temporary"),
        "ok",
    ]

    assert recovery.execute() is None
    assert recovery.failure_count == 1

    assert recovery.execute() == "ok"
    assert recovery.failure_count == 0
    assert recovery.last_error is None
    assert recovery.suppressed is False
    runtime.suppress_current_occurrence.assert_not_called()


def test_suppression_happens_only_after_retry_budget():
    recovery, runtime, clock = _recovery(max_retries=2, delay=0)
    runtime.tick.side_effect = SchedulerRuntimeError("broken file")

    recovery.execute()
    runtime.suppress_current_occurrence.assert_not_called()

    recovery.execute()
    runtime.suppress_current_occurrence.assert_called_once_with()
    assert recovery.suppressed is True


def test_reset_allows_new_retry_budget():
    recovery, runtime, clock = _recovery(max_retries=1, delay=0)
    runtime.tick.side_effect = SchedulerRuntimeError("failure")

    recovery.execute()
    assert recovery.suppressed is True

    recovery.reset()
    assert recovery.failure_count == 0
    assert recovery.suppressed is False
    assert recovery.last_error is None


def test_worker_can_use_recovery_strategy():
    from app.services.automation_worker import AutomationWorker

    runtime = MagicMock()
    recovery = MagicMock()
    recovery.execute.return_value = "recovered-result"

    worker = AutomationWorker(
        runtime,
        interval_seconds=0.01,
        recovery=recovery,
    )

    assert worker.run_once() == "recovered-result"
    recovery.execute.assert_called_once_with()
    runtime.tick.assert_not_called()


def test_runtime_occurrence_can_be_suppressed():
    from app.services.scheduler_runtime import SchedulerRuntime

    runtime = object.__new__(SchedulerRuntime)
    runtime._lock = __import__("threading").RLock()
    runtime._attempted_occurrence = (42, __import__("datetime").datetime(2026, 8, 19, 10, 0))
    runtime._suppressed_occurrence = None
    runtime._started_occurrence = None

    assert runtime.suppress_current_occurrence() is True
    assert runtime._suppressed_occurrence == runtime._attempted_occurrence
