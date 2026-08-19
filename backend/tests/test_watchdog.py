from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.services.watchdog import HealthStatus, PlaybackWatchdog


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def make_watchdog(timeout=10.0, check=1.0, recovery=None):
    runtime = MagicMock()
    clock = FakeClock()
    watchdog = PlaybackWatchdog(
        runtime,
        stall_timeout_seconds=timeout,
        check_interval_seconds=check,
        clock=clock,
        recovery=recovery,
    )
    return watchdog, runtime, clock


def test_rejects_invalid_configuration():
    runtime = MagicMock()

    with pytest.raises(ValueError):
        PlaybackWatchdog(runtime, stall_timeout_seconds=0)

    with pytest.raises(ValueError):
        PlaybackWatchdog(runtime, check_interval_seconds=0)


def test_idle_is_not_a_failure():
    watchdog, runtime, clock = make_watchdog()

    assert watchdog.check_once() == HealthStatus.IDLE
    assert watchdog.status == HealthStatus.IDLE


def test_playback_start_sets_healthy():
    watchdog, runtime, clock = make_watchdog()

    watchdog.notify_playback_started()

    assert watchdog.status == HealthStatus.HEALTHY
    assert watchdog.check_once() == HealthStatus.HEALTHY


def test_heartbeat_keeps_playback_healthy():
    watchdog, runtime, clock = make_watchdog(timeout=10)

    watchdog.notify_playback_started()
    clock.advance(9)
    watchdog.heartbeat()

    clock.advance(9)

    assert watchdog.check_once() == HealthStatus.HEALTHY


def test_stall_is_detected_after_timeout():
    watchdog, runtime, clock = make_watchdog(timeout=10)

    watchdog.notify_playback_started()
    clock.advance(11)

    assert watchdog.check_once() == HealthStatus.STALLED
    assert watchdog.recovery_count == 1


def test_stall_triggers_recovery_callback():
    recovery = MagicMock()
    watchdog, runtime, clock = make_watchdog(timeout=10, recovery=recovery)

    watchdog.notify_playback_started()
    clock.advance(11)

    watchdog.check_once()

    recovery.assert_called_once_with()
    assert watchdog.recovery_count == 1


def test_recovery_can_restore_healthy_state():
    watchdog_ref = {}

    def recovery():
        watchdog_ref["watchdog"].notify_playback_started()

    watchdog, runtime, clock = make_watchdog(
        timeout=10,
        recovery=recovery,
    )
    watchdog_ref["watchdog"] = watchdog

    watchdog.notify_playback_started()
    clock.advance(11)

    assert watchdog.check_once() == HealthStatus.HEALTHY
    assert watchdog.recovery_count == 1


def test_failed_recovery_leaves_stalled_status():
    recovery = MagicMock(side_effect=RuntimeError("recovery failed"))
    watchdog, runtime, clock = make_watchdog(timeout=10, recovery=recovery)

    watchdog.notify_playback_started()
    clock.advance(11)

    assert watchdog.check_once() == HealthStatus.STALLED
    assert watchdog.last_recovery_error == "recovery failed"


def test_stop_returns_to_idle():
    watchdog, runtime, clock = make_watchdog()

    watchdog.notify_playback_started()
    watchdog.notify_playback_stopped()

    assert watchdog.status == HealthStatus.IDLE
    clock.advance(100)
    assert watchdog.check_once() == HealthStatus.IDLE


def test_heartbeat_ignored_when_playback_is_not_expected():
    watchdog, runtime, clock = make_watchdog()

    watchdog.heartbeat()

    assert watchdog.status == HealthStatus.IDLE


def test_start_is_idempotent_and_stop_is_safe():
    watchdog, runtime, clock = make_watchdog(check=0.01)

    assert watchdog.start() is True
    assert watchdog.start() is False
    time.sleep(0.03)

    assert watchdog.is_running is True
    assert watchdog.stop() is True
    assert watchdog.is_running is False
    assert watchdog.stop() is False


def test_shutdown_alias():
    watchdog, runtime, clock = make_watchdog(check=0.01)

    watchdog.start()
    assert watchdog.shutdown() is True
    assert watchdog.is_running is False


def test_watchdog_does_not_create_or_stop_audio_engine():
    watchdog, runtime, clock = make_watchdog()

    watchdog.notify_playback_started()
    clock.advance(11)
    watchdog.check_once()

    runtime.engine.assert_not_called()
    runtime.stop.assert_not_called()
