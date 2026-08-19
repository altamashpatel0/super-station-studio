from __future__ import annotations

import logging
import threading
from typing import Optional, Protocol

from .scheduler_runtime import SchedulerRuntime

logger = logging.getLogger(__name__)


class TickRecovery(Protocol):
    def execute(self) -> object:
        ...


class AutomationWorkerError(Exception):
    """Base error for the V0.7 automation worker."""


class AutomationWorker:
    """
    Owns the 24/7 automation loop for the existing SchedulerRuntime.

    V0.6 SchedulerRuntime already knows how to resolve a schedule and start
    the selected target. This worker deliberately does not duplicate that
    logic. It only owns the long-running lifecycle:

        start -> poll SchedulerRuntime.tick() -> stop

    The worker is intentionally independent from FastAPI and AudioEngine.
    That keeps the station automation testable and lets later V0.7 parts add
    recovery/watchdog behaviour without changing the scheduler domain logic.
    """

    DEFAULT_INTERVAL_SECONDS = 0.25

    def __init__(
        self,
        runtime: SchedulerRuntime,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        recovery: Optional[TickRecovery] = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero.")

        self._runtime = runtime
        self._interval = float(interval_seconds)
        self._recovery = recovery

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._tick_count = 0
        self._last_error: Optional[str] = None

    @property
    def runtime(self) -> SchedulerRuntime:
        return self._runtime

    @property
    def interval_seconds(self) -> float:
        return self._interval

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def tick_count(self) -> int:
        with self._lock:
            return self._tick_count

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def start(self) -> bool:
        """
        Start the automation worker.

        Returns True when a new worker thread was started and False when the
        worker was already running.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._stop_event.clear()
            self._last_error = None

            self._thread = threading.Thread(
                target=self._run,
                name="automation-worker",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> bool:
        """
        Stop the worker gracefully.

        The worker never stops or shuts down the AudioEngine. Playback
        lifecycle remains owned by SchedulerRuntime/AudioEngine.
        """
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

    def run_once(self) -> object:
        """
        Execute one scheduler tick synchronously.

        This is useful for deterministic tests and operator/manual execution.
        """
        try:
            result = (
                self._recovery.execute()
                if self._recovery is not None
                else self._runtime.tick()
            )
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            raise

        with self._lock:
            self._tick_count += 1
            self._last_error = None

        return result

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.run_once()
            except Exception:
                # A single scheduler/runtime failure must not terminate the
                # 24/7 worker. The optional recovery policy decides whether
                # this was a retryable failure or the current occurrence
                # should be suppressed.
                logger.exception("Automation worker tick failed.")

    def shutdown(self) -> bool:
        """Lifecycle alias for stop()."""
        return self.stop()

    def __enter__(self) -> "AutomationWorker":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
