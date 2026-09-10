from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.engine import AudioEngine

from ..database.database import session_scope
from ..services.asset_playback_manager import AssetPlaybackManager
from ..services.clock_wheel import ClockWheel
from .playback_controller import PlaybackController, PlaybackSource
from .queue_manager import QueueManager
from .playback_history import PlaybackHistoryRecorder
from ..services.scheduler_selection import (
    SelectionError,
    SelectionResult,
    select_for_current_schedule,
)

logger = logging.getLogger(__name__)


class SchedulerRuntimeError(Exception):
    """Base error for scheduler runtime failures."""


class SchedulerRuntime:
    """
    Runtime bridge between the deterministic scheduler and playback.

    Responsibilities:
      * resolve the schedule active at a given time;
      * select an eligible target;
      * start that target through the existing AudioEngine or
        AssetPlaybackManager;
      * avoid starting the same schedule occurrence repeatedly;
      * optionally poll in a background thread.

    ClockWheel remains read-only and does not start playback. This class is
    the runtime layer that performs the actual transition into playback.
    """

    POLL_INTERVAL_SECONDS = 0.25

    def __init__(
        self,
        engine: AudioEngine,
        asset_playback_manager: AssetPlaybackManager,
        controller: PlaybackController | None = None,
        queue_manager: QueueManager | None = None,
        history_recorder: PlaybackHistoryRecorder | None = None,
        *,
        session_factory: Callable[[], Session] = session_scope,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero.")

        self._engine = engine
        self._asset_manager = asset_playback_manager
        self._controller = controller
        self._queue_manager = queue_manager
        self._history_recorder = history_recorder
        if self._controller is not None:
            self._controller.register_preempt_handler(
                PlaybackSource.SCHEDULE,
                self._on_preempted,
            )
        self._session_factory = session_factory
        self._poll_interval = float(poll_interval_seconds)

        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Identity of the occurrence that was most recently started.
        self._started_occurrence: Optional[tuple[int, dt.datetime]] = None
        self._attempted_occurrence: Optional[tuple[int, dt.datetime]] = None
        self._suppressed_occurrence: Optional[tuple[int, dt.datetime]] = None
        self._playlist_occurrence_key: Optional[tuple[int, dt.datetime]] = None
        self._started_end_datetime: Optional[dt.datetime] = None

        self._last_selection: Optional[SelectionResult] = None
        self._last_error: Optional[str] = None

    @property
    def engine(self) -> AudioEngine:
        # Production playback is owned by PlaybackController. Expose its
        # active deck so watchdog/health checks follow the same deck as the
        # playback API and live UI.
        if self._controller is not None:
            return self._controller.engine
        return self._engine

    @property
    def asset_playback_manager(self) -> AssetPlaybackManager:
        return self._asset_manager

    @property
    def playback_controller(self) -> PlaybackController | None:
        return self._controller

    def get_last_selection(self) -> Optional[SelectionResult]:
        with self._lock:
            return self._last_selection

    def get_last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def tick(self, now: Optional[dt.datetime] = None) -> Optional[SelectionResult]:
        """
        Resolve and start the schedule active at ``now``.

        Calling tick repeatedly during the same schedule occurrence is safe:
        the same occurrence is started only once. When the active occurrence
        changes, the new target is started.
        """
        current = now or dt.datetime.now()

        with self._session_factory() as db:
            # Enforce the stored end boundary from the occurrence we actually
            # started. This is intentionally checked before resolving the new
            # current schedule, so an expired playlist can never continue just
            # because the clock resolver/overlap state changes at the boundary.
            if self._started_end_datetime is not None and current >= self._started_end_datetime:
                self._handle_schedule_window_end(db, current)

            occurrence = ClockWheel(db).get_current_schedule(current)
            if occurrence is None:
                self._handle_schedule_window_end(db, current)
                return None

            # If a scheduled playlist is still the active owner but its native
            # track-end callback was missed, recover the next queued song here.
            # The queue manager guards this path so it cannot race the normal
            # completion callback.
            if self._queue_manager is not None and self._queue_manager.scheduled_playlist_active:
                self._queue_manager.ensure_scheduled_continuation(db)

            occurrence_key = (
                occurrence.schedule_id,
                occurrence.start_datetime,
            )

            with self._lock:
                if self._playlist_occurrence_key is not None and self._playlist_occurrence_key != occurrence_key:
                    self._playlist_occurrence_key = None
                if self._started_occurrence == occurrence_key:
                    return self._last_selection
                if self._suppressed_occurrence == occurrence_key:
                    return None
                self._attempted_occurrence = occurrence_key

            try:
                selection = select_for_current_schedule(db, current)
                if selection is None:
                    return None
                self._start_selection(db, selection, occurrence_key=occurrence_key)
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                logger.exception(
                    "Failed to start scheduled target for schedule %s",
                    occurrence.schedule_id,
                )
                raise SchedulerRuntimeError(
                    f"Failed to start schedule {occurrence.schedule_id}: {exc}"
                ) from exc

            with self._lock:
                self._started_occurrence = occurrence_key
                self._started_end_datetime = occurrence.end_datetime
                self._last_selection = selection
                self._last_error = None

            return selection

    def _handle_schedule_window_end(self, db: Session, now: dt.datetime) -> None:
        """Pause bounded scheduled playback exactly when its schedule expires.

        The scheduler is intentionally allowed to schedule content longer than
        its time window. When the window closes, the current scheduled item is
        paused and scheduler ownership is released so the next schedule or a
        manual operator action can take over normally. Remaining items from a
        scheduled playlist are discarded because they belong to the expired
        window.
        """
        with self._lock:
            started = self._started_occurrence
            controller = self._controller
            queue_manager = self._queue_manager

        if started is None or controller is None:
            return
        if controller.active_source != PlaybackSource.SCHEDULE:
            return

        pause_failed = False
        try:
            status = controller.engine.get_status()
            state_name = getattr(getattr(status, "state", None), "name", str(getattr(status, "state", "")))
            if state_name == "PLAYING":
                controller.pause()
        except Exception:
            pause_failed = True
            logger.exception("Failed to pause scheduled playback at schedule end")

        # The time boundary is authoritative. If pause itself fails (for
        # example because the audio device is already transitioning), do not
        # return early and leave the scheduled queue alive. Fall back to a
        # controlled stop so the expired programme can never continue.
        if pause_failed:
            try:
                if controller.active_source == PlaybackSource.SCHEDULE:
                    controller.stop(PlaybackSource.SCHEDULE)
            except Exception:
                logger.exception("Failed to stop scheduled playback after pause failure")

        if queue_manager is not None and queue_manager.scheduled_playlist_active:
            try:
                queue_manager.end_scheduled_playlist(db)
            except Exception:
                logger.exception("Failed to finalize scheduled playlist at schedule end")

        if self._history_recorder is not None:
            self._history_recorder.finish_active_as_skipped(
                "Scheduled playback window ended before the item completed."
            )

        try:
            db.commit()
        except Exception:
            logger.exception("Failed to commit scheduler end-of-window state")

        controller.release_if_owned(PlaybackSource.SCHEDULE)
        with self._lock:
            self._playlist_occurrence_key = None
            self._started_occurrence = None
            self._started_end_datetime = None
            self._attempted_occurrence = None
            self._suppressed_occurrence = None
            self._last_selection = None
            self._last_error = None

    def _start_selection(
        self,
        db: Session,
        selection: SelectionResult,
        *,
        occurrence_key: tuple[int, dt.datetime],
    ) -> None:
        """
        Start one selected item.

        Jingles and advertisements must go through AssetPlaybackManager so
        cooldown/history state is recorded. Songs and playlist-selected songs
        use the existing AudioEngine directly.
        """
        if selection.target_type == "PLAYLIST" and self._queue_manager is not None:
            self._queue_manager.start_scheduled_playlist(db, selection.target_id)
            with self._lock:
                self._playlist_occurrence_key = occurrence_key
            return

        if self._controller is not None:
            # A preemption callback may persist the outgoing queue item using
            # another SQLAlchemy session. Ensure this scheduler session has no
            # pending write transaction before entering PlaybackController.
            db.commit()
            if selection.selected_kind in {"JINGLE", "ADVERTISEMENT", "PROMO"}:
                self._controller.start(
                    PlaybackSource.SCHEDULE,
                    lambda: self._asset_manager.play_asset(
                        db,
                        selection.selected_id,
                        source=PlaybackSource.SCHEDULE,
                    ),
                )
                return

            self._controller.start_track(
                PlaybackSource.SCHEDULE,
                selection.selected_file_path,
            )
            return

        # Backward-compatible standalone/test mode.
        if selection.selected_kind in {"JINGLE", "ADVERTISEMENT", "PROMO"}:
            self._asset_manager.play_asset(db, selection.selected_id)
            return

        self._engine.load_track(selection.selected_file_path)
        self._engine.play()

    def _on_preempted(
        self,
        previous: PlaybackSource,
        new: PlaybackSource,
    ) -> None:
        # Manual playback intentionally cancels the currently active
        # schedule occurrence. A later schedule occurrence can start normally.
        if new == PlaybackSource.MANUAL:
            self.suppress_current_occurrence()

    def is_playlist_occurrence_active(self) -> bool:
        with self._lock:
            return self._playlist_occurrence_key is not None

    def start(self) -> None:
        """Start the background scheduler loop. Safe to call repeatedly."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="scheduler-runtime",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the background loop without touching the playback engine."""
        with self._lock:
            thread = self._thread
            self._stop_event.set()

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

        with self._lock:
            if self._thread is thread and (
                thread is None or not thread.is_alive()
            ):
                self._thread = None

    def reset_occurrence(self) -> None:
        """
        Clear the duplicate-start guard.

        Useful after an operator manually changes playback and wants the
        currently active schedule to be eligible again.
        """
        with self._lock:
            self._started_occurrence = None
            self._started_end_datetime = None
            self._attempted_occurrence = None
            self._suppressed_occurrence = None
            self._playlist_occurrence_key = None

    def suppress_current_occurrence(self) -> bool:
        """Suppress the occurrence that most recently failed to start.

        Returns True when an occurrence was available to suppress.
        The active AudioEngine is never stopped by this method.
        """
        with self._lock:
            if self._attempted_occurrence is None:
                return False
            self._suppressed_occurrence = self._attempted_occurrence
            self._started_occurrence = None
            return True

    def get_attempted_occurrence(self) -> Optional[tuple[int, dt.datetime]]:
        with self._lock:
            return self._attempted_occurrence

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                self.tick()
            except Exception:
                # Runtime failures are recorded by tick(). The scheduler loop
                # must remain alive so a transient target/device problem does
                # not permanently disable scheduling.
                logger.exception("Scheduler runtime tick failed.")

    def shutdown(self) -> None:
        """Alias for stop(), provided for lifecycle symmetry."""
        self.stop()

    def __enter__(self) -> "SchedulerRuntime":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
