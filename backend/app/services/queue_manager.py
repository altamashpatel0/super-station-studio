"""
app/services/queue_manager.py
================================

The V0.3 "final integration" piece: connects the runtime Playback
Queue (`QueueRepository` / `QueueItem`) to the existing, unmodified
V0.1 `AudioEngine` (`src/engine.py`).

This module contains NO playback logic of its own and NO duplicate
audio engine - it only reacts to the engine's existing
`on_track_end(reason)` hook and drives the queue + engine through
their existing public APIs:

    V0.1 AudioEngine --on_track_end(TrackEndReason)--> QueueManager
                                                            |
                                                  find next QUEUED item
                                                            |
                                                  engine.load_track() + engine.play()
                                                            |
                                                  mark queue item PLAYING

Required flow (natural completion)
-----------------------------------
1. Engine finishes a track naturally -> fires `on_track_end(COMPLETED)`.
2. The just-finished queue item -> PLAYED.
3. The next `QUEUED` item (by position) is loaded and played.
4. That item -> PLAYING.
5. If there is no next `QUEUED` item, the engine is stopped cleanly and
   the queue is left empty of anything PLAYING.

Manual stop
-----------
`AudioEngine.stop()` (called from `POST /api/playback/stop`, or
internally by this module when the queue empties) also fires
`on_track_end`, but with `TrackEndReason.MANUAL_STOP`. This is
deliberately handled *differently*: the current item is marked
`SKIPPED` and playback does **not** advance to the next track. Manual
stop must never auto-play - see module-level tests in
`tests/test_queue_engine_integration.py`.

Failure handling
----------------
Both "start the queue" (`play_from_queue`) and "advance after a track
finished" (internal) treat a track that can't actually be played
(missing file, engine raises `AudioEngineError` on load/play) the same
way: mark that queue item `FAILED` and try the *next* `QUEUED` item,
recursively, until one plays successfully or the queue is exhausted -
at which point playback stops cleanly, exactly like a normal
queue-completion.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.engine import AudioEngine
from src.models import AudioEngineError, TrackEndReason

from ..database.database import session_scope
from ..database.models import QueueItem, QueueItemStatus
from ..database.repositories.queue_repository import QueueRepository
from ..database.repositories.song_repository import SongRepository

logger = logging.getLogger(__name__)


class QueueManagerError(Exception):
    """Base class for QueueManager-raised errors."""


class QueueEmptyError(QueueManagerError):
    """Raised when there is no playable `QUEUED` item to start."""


class QueueItemNotQueuedError(QueueManagerError):
    """Raised when a specific queue_item_id was requested but isn't QUEUED."""


class QueueManager:
    """Bridges the V0.3 Playback Queue to the shared V0.1 `AudioEngine`."""

    def __init__(self, engine: AudioEngine) -> None:
        self._engine = engine
        # Single subscription for the lifetime of this manager. Using
        # `on_track_end` (not the narrower `on_track_complete`) because
        # we need to tell COMPLETED apart from MANUAL_STOP - see the
        # module docstring.
        self._engine.on_track_end(self._on_track_end)

    # ------------------------------------------------------------------
    # Public entry points (called from API routes, with a request-scoped
    # `db` session)
    # ------------------------------------------------------------------

    def play_from_queue(self, db: Session, queue_item_id: Optional[int] = None) -> dict:
        """
        Start playback from the queue.

        - `queue_item_id=None` (default): start the first `QUEUED` item
          in position order.
        - `queue_item_id=<id>`: start that specific item, which must
          currently be `QUEUED`.

        On success, returns the engine's `PlaybackStatus.to_dict()` for
        the track that ended up playing (which, thanks to
        failure-skipping, may not be the item originally requested).

        Raises:
            QueueEmptyError: nothing playable was found (empty queue,
                or every remaining item failed to load/play).
            QueueItemNotQueuedError: `queue_item_id` doesn't exist or
                isn't `QUEUED`.
        """
        repo = QueueRepository(db)

        if queue_item_id is not None:
            target = repo.get_by_id(queue_item_id)
            if target is None or self._status(target) != QueueItemStatus.QUEUED:
                raise QueueItemNotQueuedError(
                    f"Queue item {queue_item_id} does not exist or is not QUEUED."
                )
        else:
            target = self._first_queued(repo)
            if target is None:
                raise QueueEmptyError("The queue is empty; nothing to play.")

        result = self._start_item(db, target)
        if result is None:
            raise QueueEmptyError("No playable track remained in the queue.")
        return result

    # ------------------------------------------------------------------
    # Internal: engine event handling (fires on whatever thread the
    # engine/player call back on - synchronous within stop()/the
    # output's finished-callback, so we open our own short-lived DB
    # session rather than relying on a request-scoped one)
    # ------------------------------------------------------------------

    def _on_track_end(self, reason: TrackEndReason) -> None:
        if reason == TrackEndReason.COMPLETED:
            try:
                with session_scope() as db:
                    self._advance_after_completion(db)
            except Exception:  # pragma: no cover - defensive
                logger.exception("QueueManager failed to auto-advance after track completion")
        elif reason == TrackEndReason.MANUAL_STOP:
            try:
                with session_scope() as db:
                    self._mark_current_skipped(db)
            except Exception:  # pragma: no cover - defensive
                logger.exception("QueueManager failed to record a manual stop")
        # TrackEndReason.ERROR is raised synchronously back to whoever
        # called engine.play() (see Player.play()), and `_start_item`
        # below already catches AudioEngineError around that same call,
        # marking the item FAILED and advancing itself - handling it
        # again here would just double-process the same failure.

    def _advance_after_completion(self, db: Session) -> None:
        repo = QueueRepository(db)
        current = self._current_playing(repo)
        if current is not None:
            current.status = QueueItemStatus.PLAYED.value
            db.flush()

        next_item = self._first_queued(repo)
        if next_item is None:
            self._stop_cleanly()
            return

        self._start_item(db, next_item)

    def _mark_current_skipped(self, db: Session) -> None:
        repo = QueueRepository(db)
        current = self._current_playing(repo)
        if current is not None:
            current.status = QueueItemStatus.SKIPPED.value
            db.flush()

    # ------------------------------------------------------------------
    # Internal: starting a queue item on the engine, with cascading
    # failure-skip
    # ------------------------------------------------------------------

    def _start_item(self, db: Session, item: QueueItem) -> Optional[dict]:
        song_repo = SongRepository(db)
        song = song_repo.get_by_id(item.song_id)

        if song is None or not song.enabled:
            logger.warning(
                "Queue item %s references song %s, which is missing/unavailable; skipping.",
                item.id,
                item.song_id,
            )
            item.status = QueueItemStatus.FAILED.value
            db.flush()
            return self._advance_past_failure(db)

        try:
            self._engine.load_track(song.file_path)
            status = self._engine.play()
        except AudioEngineError as exc:
            logger.warning("Failed to play queue item %s (%s): %s", item.id, song.file_path, exc)
            item.status = QueueItemStatus.FAILED.value
            db.flush()
            return self._advance_past_failure(db)

        item.status = QueueItemStatus.PLAYING.value
        db.flush()
        song_repo.record_play(song.id)
        db.flush()
        return status.to_dict()

    def _advance_past_failure(self, db: Session) -> Optional[dict]:
        repo = QueueRepository(db)
        next_item = self._first_queued(repo)
        if next_item is None:
            self._stop_cleanly()
            return None
        return self._start_item(db, next_item)

    def _stop_cleanly(self) -> None:
        """Stop the engine if it's actually doing something. Safe to call
        when the engine is already IDLE/STOPPED (e.g. right after a
        natural completion already parked it in STOPPED)."""
        try:
            self._engine.stop()
        except AudioEngineError:
            logger.debug("Engine was already stopped/idle while emptying the queue.")

    # ------------------------------------------------------------------
    # Internal: small queries over the queue
    # ------------------------------------------------------------------

    @staticmethod
    def _status(item: QueueItem) -> QueueItemStatus:
        return item.status if isinstance(item.status, QueueItemStatus) else QueueItemStatus(item.status)

    def _current_playing(self, repo: QueueRepository) -> Optional[QueueItem]:
        for item in repo.list_all():
            if self._status(item) == QueueItemStatus.PLAYING:
                return item
        return None

    def _first_queued(self, repo: QueueRepository) -> Optional[QueueItem]:
        for item in repo.list_all():
            if self._status(item) == QueueItemStatus.QUEUED:
                return item
        return None
