from __future__ import annotations

import logging
import threading
from typing import Optional

from src.models import TrackEndReason

from .scheduler_runtime import SchedulerRuntime
from .playback_controller import PlaybackController, PlaybackSource

logger = logging.getLogger(__name__)


class PlaybackContinuationError(Exception):
    """Base error for scheduler playback-continuation failures."""


class PlaybackContinuation:
    """
    V0.7 Part 2 bridge between AudioEngine completion events and the
    existing SchedulerRuntime occurrence guard.

    V0.6 SchedulerRuntime intentionally starts each schedule occurrence only
    once. V0.7 Part 2 adds one missing transition: when the current item
    naturally completes, the current occurrence becomes eligible for another
    scheduler tick.

    Manual stop and playback error do NOT trigger continuation.

    The class does not create an audio engine, does not directly play audio,
    and does not alter Queue/Crossfade behaviour.
    """

    def __init__(self, runtime: SchedulerRuntime) -> None:
        self._runtime = runtime
        controller = getattr(runtime, "playback_controller", None)
        self._controller: PlaybackController | None = (
            controller if isinstance(controller, PlaybackController) else None
        )
        self._lock = threading.RLock()
        self._running = False
        self._last_reason: Optional[TrackEndReason] = None

    @property
    def runtime(self) -> SchedulerRuntime:
        return self._runtime

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def last_reason(self) -> Optional[TrackEndReason]:
        with self._lock:
            return self._last_reason

    def attach(self) -> None:
        """
        Register the completion callback exactly once.

        AudioEngine is obtained from SchedulerRuntime, so this continuation
        layer shares the exact same engine used by scheduler playback.
        """
        with self._lock:
            if self._running:
                return

            if self._controller is not None:
                self._controller.register_completion_handler(
                    PlaybackSource.SCHEDULE,
                    self._on_track_end,
                )
            else:
                self._runtime.engine.on_track_end(self._on_track_end)
            self._running = True

    def detach(self) -> None:
        """
        Mark the bridge inactive.

        AudioEngine intentionally has no callback-removal API in V0.1, so
        detach is a lifecycle flag rather than callback unregistration.
        """
        with self._lock:
            self._running = False

    def _on_track_end(self, reason: TrackEndReason) -> None:
        with self._lock:
            if not self._running:
                return
            self._last_reason = reason

        # Only a natural completion means the scheduler should continue.
        # MANUAL_STOP and ERROR must remain terminal for the current run.
        if reason != TrackEndReason.COMPLETED:
            return

        # A scheduled playlist is materialized into the runtime queue and
        # QueueManager advances it track-by-track. Resetting the schedule
        # occurrence here would restart the playlist from track 1.
        try:
            is_playlist_occurrence_active = getattr(self._runtime, "is_playlist_occurrence_active", None)
            if callable(is_playlist_occurrence_active) and is_playlist_occurrence_active() is True:
                return
        except Exception:
            logger.exception("Failed to inspect scheduler playlist state")

        try:
            self._runtime.reset_occurrence()
        except Exception:
            logger.exception("Failed to reset scheduler occurrence after completion.")

    def shutdown(self) -> None:
        self.detach()

    def __enter__(self) -> "PlaybackContinuation":
        self.attach()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.detach()
