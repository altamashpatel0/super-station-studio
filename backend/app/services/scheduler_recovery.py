from __future__ import annotations

import threading
import time
from typing import Optional

from .scheduler_runtime import SchedulerRuntime, SchedulerRuntimeError


class SchedulerRecoveryError(Exception):
    """Base class for scheduler failure-recovery errors."""


class SchedulerFailureRecovery:
    """
    V0.7 Part 3 recovery policy.

    A failed scheduler tick is retried a bounded number of times. Retries
    use a small backoff so a broken file/device cannot create a tight loop.
    Once the retry budget is exhausted, the exact failed schedule occurrence
    is suppressed and the worker continues running. A later schedule
    occurrence is not suppressed.

    This class does not stop/restart AudioEngine and does not mutate Queue or
    AssetPlayback state.
    """

    def __init__(
        self,
        runtime: SchedulerRuntime,
        *,
        max_retries: int = 3,
        retry_delay_seconds: float = 0.25,
        clock=time.monotonic,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative.")

        self._runtime = runtime
        self._max_retries = int(max_retries)
        self._retry_delay = float(retry_delay_seconds)
        self._clock = clock
        self._lock = threading.RLock()

        self._failure_count = 0
        self._next_retry_at = 0.0
        self._last_error: Optional[str] = None
        self._suppressed = False

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    @property
    def suppressed(self) -> bool:
        with self._lock:
            return self._suppressed

    def execute(self) -> object:
        """Run one recovered scheduler tick."""
        now = self._clock()

        with self._lock:
            if now < self._next_retry_at:
                return None

        try:
            result = self._runtime.tick()
        except SchedulerRuntimeError as exc:
            with self._lock:
                self._failure_count += 1
                self._last_error = str(exc)

                if self._failure_count >= self._max_retries:
                    self._runtime.suppress_current_occurrence()
                    self._suppressed = True
                    self._next_retry_at = 0.0
                else:
                    self._next_retry_at = now + self._retry_delay

            return None

        with self._lock:
            self._failure_count = 0
            self._last_error = None
            self._suppressed = False
            self._next_retry_at = 0.0

        return result

    def reset(self) -> None:
        """Clear recovery counters, allowing a fresh retry budget."""
        with self._lock:
            self._failure_count = 0
            self._last_error = None
            self._suppressed = False
            self._next_retry_at = 0.0
