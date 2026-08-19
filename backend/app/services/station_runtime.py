from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from src.models import PlayerState

from .automation_worker import AutomationWorker
from .playback_continuation import PlaybackContinuation
from .scheduler_recovery import SchedulerFailureRecovery
from .scheduler_runtime import SchedulerRuntime
from .watchdog import HealthStatus, PlaybackWatchdog

logger = logging.getLogger(__name__)


class StationRuntimeError(Exception):
    """Base error for the V0.7 station lifecycle."""


class StationRuntime:
    """
    V0.7 Part 5 — owns the complete 24/7 automation lifecycle.

    Start order:
        PlaybackContinuation -> Watchdog -> AutomationWorker

    Stop order:
        AutomationWorker -> Watchdog -> PlaybackContinuation

    AudioEngine remains owned by the existing engine provider and is only
    shut down by FastAPI's application shutdown handler.

    A small health bridge samples AudioEngine playback position. A changing
    position is a heartbeat; a PLAYING state with no position progress is
    allowed to become a watchdog stall. This avoids declaring a healthy,
    advancing track stalled while still detecting a frozen player.
    """

    def __init__(
        self,
        runtime: SchedulerRuntime,
        *,
        recovery: Optional[SchedulerFailureRecovery] = None,
        worker: Optional[AutomationWorker] = None,
        continuation: Optional[PlaybackContinuation] = None,
        watchdog: Optional[PlaybackWatchdog] = None,
        health_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if health_interval_seconds <= 0:
            raise ValueError("health_interval_seconds must be greater than zero.")

        self._runtime = runtime
        self._recovery = recovery or SchedulerFailureRecovery(runtime)
        self._worker = worker or AutomationWorker(runtime, recovery=self._recovery)
        self._continuation = continuation or PlaybackContinuation(runtime)
        self._watchdog = watchdog or PlaybackWatchdog(
            runtime,
            recovery=self._recover_stalled_playback,
        )

        self._health_interval = float(health_interval_seconds)
        self._clock = clock
        self._lock = threading.RLock()
        self._health_stop = threading.Event()
        self._health_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_position: Optional[float] = None
        self._last_file_path: Optional[str] = None

    @property
    def runtime(self) -> SchedulerRuntime:
        return self._runtime

    @property
    def worker(self) -> AutomationWorker:
        return self._worker

    @property
    def continuation(self) -> PlaybackContinuation:
        return self._continuation

    @property
    def watchdog(self) -> PlaybackWatchdog:
        return self._watchdog

    @property
    def recovery(self) -> SchedulerFailureRecovery:
        return self._recovery

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._health_stop.clear()
            self._last_position = None
            self._last_file_path = None

        try:
            # Completion listener must exist before worker can start playback.
            self._continuation.attach()
            self._watchdog.start()
            self._start_health_bridge()
            self._worker.start()
        except Exception:
            self.stop()
            raise

        return True

    def stop(self, timeout: float = 2.0) -> bool:
        with self._lock:
            was_running = self._running
            self._running = False
            self._health_stop.set()

        # Stop the producer first; no new schedule ticks should start while
        # lifecycle components are being detached.
        self._worker.stop(timeout=timeout)
        self._watchdog.stop(timeout=timeout)
        self._stop_health_bridge(timeout=timeout)
        self._continuation.detach()

        return was_running

    def shutdown(self, timeout: float = 2.0) -> bool:
        return self.stop(timeout=timeout)

    def _start_health_bridge(self) -> None:
        with self._lock:
            if self._health_thread is not None and self._health_thread.is_alive():
                return

            self._health_thread = threading.Thread(
                target=self._health_loop,
                name="station-health-bridge",
                daemon=True,
            )
            self._health_thread.start()

    def _stop_health_bridge(self, timeout: float = 2.0) -> None:
        with self._lock:
            thread = self._health_thread

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

        with self._lock:
            if self._health_thread is thread and (
                thread is None or not thread.is_alive()
            ):
                self._health_thread = None

    def _health_loop(self) -> None:
        while not self._health_stop.wait(self._health_interval):
            try:
                self._sample_playback()
            except Exception:
                logger.exception("Station health bridge sample failed.")

    def _sample_playback(self) -> None:
        status = self._runtime.engine.get_status()

        if status.state != PlayerState.PLAYING:
            self._last_position = None
            self._last_file_path = status.file_path
            self._watchdog.notify_playback_stopped()
            return

        position = float(status.position_seconds)
        file_path = status.file_path

        if file_path != self._last_file_path:
            self._last_file_path = file_path
            self._last_position = position
            self._watchdog.notify_playback_started(timestamp=self._clock())
            return

        if self._last_position is None:
            self._last_position = position
            self._watchdog.notify_playback_started(timestamp=self._clock())
            return

        if position > self._last_position:
            self._watchdog.heartbeat(timestamp=self._clock())

        self._last_position = position

    def _recover_stalled_playback(self) -> None:
        # Do not stop/restart AudioEngine here. Re-arm the current scheduler
        # occurrence so the existing worker can select/start the next target.
        self._runtime.reset_occurrence()
        self._recovery.reset()

    def __enter__(self) -> "StationRuntime":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
