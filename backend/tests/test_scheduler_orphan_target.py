from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.services.scheduler_recovery import SchedulerFailureRecovery
from app.services.scheduler_runtime import SchedulerRuntime, SchedulerRuntimeError


@contextmanager
def _db_context(db):
    yield db


def _runtime():
    engine = MagicMock()
    asset_manager = MagicMock()
    controller = None
    db = MagicMock()
    runtime = SchedulerRuntime(
        engine,
        asset_manager,
        controller=controller,
        session_factory=lambda: _db_context(db),
        poll_interval_seconds=0.01,
    )
    return runtime, db


def test_orphaned_schedule_target_is_recoverable(monkeypatch):
    runtime, db = _runtime()

    occurrence = MagicMock(
        schedule_id=42,
        start_datetime=dt.datetime(2026, 8, 26, 18, 30),
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: occurrence,
    )

    from app.services import scheduler_runtime as runtime_module
    from app.services.scheduler_selection import TargetNotFoundError

    monkeypatch.setattr(
        runtime_module,
        "select_for_current_schedule",
        lambda db, now: (_ for _ in ()).throw(
            TargetNotFoundError("No playlist with id 2.")
        ),
    )

    recovery = SchedulerFailureRecovery(
        runtime,
        max_retries=3,
        retry_delay_seconds=0,
    )

    assert recovery.execute() is None
    assert recovery.failure_count == 1
    assert "No playlist with id 2." in (runtime.get_last_error() or "")

    assert recovery.execute() is None
    assert recovery.failure_count == 2

    assert recovery.execute() is None
    assert recovery.failure_count == 3
    assert recovery.suppressed is True
    assert recovery.suppressed is True
