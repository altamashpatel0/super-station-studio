from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Callable, Optional

from .scheduler_runtime import SchedulerRuntime

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    IDLE = "IDLE"
    HEALTHY = "HEALTHY"
    STALLED = "STALLED"
    RECOVERING = "RECOVERING"


class WatchdogError(Exception):
    """Base error for V0.7 Part 4 watchdog failures."""


class PlaybackWatchdog:
    """
    V0.7 Part 4 — playback health watchdog.

    The watchdog does not own audio playback and never creates another
    AudioEngine. It observes the existing runtime/engine and uses a heartbeat
    timestamp supplied by the playback layer.

    A watchdog only declares a stall when:
      * playback is expected to be active;
      * no heartbeat has been received for stall_timeout_seconds.

    IDLE/no-playback is not a failure.

    Recovery is deliberately injected as a callback. Part 4 therefore does
    not duplicate Part 3's recovery policy.
    """

    def __init__(
        self,
        runtime: SchedulerRuntime,
        *,
        stall_timeout_seconds: float = 10.0,
        check_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        recovery: Optional[Callable[[], object]] = None,
    ) -> None:
        if stall_timeout_seconds <= 0:
            raise ValueError("stall_timeout_seconds must be greater than zero.")
        if check_interval_seconds <= 0:
            raise ValueError("check_interval_seconds must be greater than zero.")

        self._runtime = runtime
        self._stall_timeout = float(stall_timeout_seconds)
        self._check_interval = float(check_interval_seconds)
        self._clock = clock
        self._recovery = recovery

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._playback_expected = False
        self._last_heartbeat: Optional[float] = None
        self._status = HealthStatus.IDLE
        self._last_recovery_error: Optional[str] = None
        self._recovery_count = 0

    @property
    def status(self) -> HealthStatus:
        with self._lock:
            return self._status

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def recovery_count(self) -> int:
        with self._lock:
            return self._recovery_count

    @property
    def last_recovery_error(self) -> Optional[str]:
        with self._lock:
            return self._last_recovery_error

    def notify_playback_started(self, *, timestamp: Optional[float] = None) -> None:
        now = self._clock() if timestamp is None else float(timestamp)
        with self._lock:
            self._playback_expected = True
            self._last_heartbeat = now
            self._status = HealthStatus.HEALTHY
            self._last_recovery_error = None

    def heartbeat(self, *, timestamp: Optional[float] = None) -> None:
        now = self._clock() if timestamp is None else float(timestamp)
        with self._lock:
            if not self._playback_expected:
                return
            self._last_heartbeat = now
            self._status = HealthStatus.HEALTHY

    def notify_playback_stopped(self) -> None:
        with self._lock:
            self._playback_expected = False
            self._last_heartbeat = None
            self._status = HealthStatus.IDLE

    def check_once(self) -> HealthStatus:
        now = self._clock()

        with self._lock:
            if not self._playback_expected:
                self._status = HealthStatus.IDLE
                return self._status

            if self._last_heartbeat is None:
                self._status = HealthStatus.HEALTHY
                return self._status

            elapsed = now - self._last_heartbeat
            if elapsed < self._stall_timeout:
                self._status = HealthStatus.HEALTHY
                return self._status

            self._status = HealthStatus.STALLED
            self._last_recovery_error = None

        self._recover()

        with self._lock:
            return self._status

    def _recover(self) -> None:
        with self._lock:
            self._status = HealthStatus.RECOVERING
            self._recovery_count += 1

        if self._recovery is None:
            with self._lock:
                self._status = HealthStatus.STALLED
            return

        try:
            self._recovery()
        except Exception as exc:
            with self._lock:
                self._last_recovery_error = str(exc)
                self._status = HealthStatus.STALLED
            logger.exception("Playback watchdog recovery failed.")
            return

        with self._lock:
            # Recovery callback is responsible for starting/continuing
            # playback and subsequently notifying the watchdog.
            if self._playback_expected and self._last_heartbeat is not None:
                self._status = HealthStatus.HEALTHY
            else:
                self._status = HealthStatus.STALLED

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="playback-watchdog",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return False
            self._stop_event.set()

        if thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

        with self._lock:
            stopped = self._thread is thread and not thread.is_alive()
            if stopped:
                self._thread = None
            return stopped

    def _run(self) -> None:
        while not self._stop_event.wait(self._check_interval):
            try:
                self.check_once()
            except Exception:
                logger.exception("Playback watchdog health check failed.")

    def shutdown(self) -> bool:
        return self.stop()

    def __enter__(self) -> "PlaybackWatchdog":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
