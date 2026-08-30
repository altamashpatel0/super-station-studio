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
from ..database.repositories.playlist_repository import PlaylistRepository
from ..database.repositories.song_repository import SongRepository
from .playback_controller import PlaybackController, PlaybackControllerError, PlaybackSource

logger = logging.getLogger(__name__)


class QueueManagerError(Exception):
    """Base class for QueueManager-raised errors."""


class QueueEmptyError(QueueManagerError):
    """Raised when there is no playable `QUEUED` item to start."""


class QueueItemNotQueuedError(QueueManagerError):
    """Raised when a specific queue_item_id was requested but isn't QUEUED."""


class QueueManager:
    """Bridges the V0.3 Playback Queue to the shared V0.1 `AudioEngine`."""

    def __init__(
        self,
        engine: AudioEngine,
        controller: PlaybackController | None = None,
    ) -> None:
        self._engine = engine
        self._controller = controller
        self._scheduled_playlist_active = False
        if self._controller is not None:
            self._controller.register_completion_handler(
                PlaybackSource.QUEUE,
                self._on_track_end,
            )
            self._controller.register_completion_handler(
                PlaybackSource.SCHEDULE,
                self._on_scheduled_track_end,
            )
            self._controller.register_preempt_handler(
                PlaybackSource.SCHEDULE,
                self._on_scheduled_preempted,
            )
            self._controller.register_preempt_handler(
                PlaybackSource.QUEUE,
                self._on_preempted,
            )
        # Standalone/test mode keeps the legacy direct subscription.
        if self._controller is None:
            # Backward-compatible standalone/test mode. Production wiring
            # always uses PlaybackController so this manager does not compete
            # with SchedulerRuntime for the AudioEngine.
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

        # A queue row is allowed to be selected directly while another queue
        # row is already playing. The old implementation passed the new track
        # straight to PlaybackController.start_track(). With the same
        # PlaybackSource (QUEUE), the controller deliberately did not
        # preempt the old source, so the underlying deck was still PLAYING and
        # load_track() could raise a 409/state conflict.
        #
        # Direct queue selection is an explicit operator action: stop the
        # current owner first, persist the old item as SKIPPED, then start the
        # requested QUEUED item. This also works when the queue currently owns
        # playback through the scheduled-playlist source.
        current = self._current_playing(repo)
        if current is not None and current.id != target.id:
            current.status = QueueItemStatus.SKIPPED.value
            db.flush()

            try:
                if self._controller is not None:
                    if self._controller.owns(PlaybackSource.QUEUE):
                        self._controller.stop(PlaybackSource.QUEUE)
                    elif self._controller.owns(PlaybackSource.SCHEDULE):
                        self._controller.stop(PlaybackSource.SCHEDULE)
                        self._scheduled_playlist_active = False
                    else:
                        # Do not steal a higher-priority source unexpectedly.
                        raise PlaybackControllerError(
                            "Queue playback cannot preempt the current playback owner."
                        )
                else:
                    self._engine.stop()
            except (AudioEngineError, PlaybackControllerError):
                # If the old deck is already stopped, continue with the
                # requested queue item. Do not turn an operator click into a
                # spurious 409.
                logger.debug("Previous playback was already stopped during direct queue selection.")

        result = self._start_item(db, target)
        if result is None:
            raise QueueEmptyError("No playable track remained in the queue.")
        return result

    def start_scheduled_playlist(self, db: Session, playlist_id: int) -> dict:
        """Replace the runtime queue with an entire scheduled playlist and start its first track.

        Scheduled playlists are queue-backed: every playlist track is materialized as a
        QueueItem in playlist order, so the Dashboard can show the complete scheduled
        program and normal queue completion/crossfade logic can advance through it.
        The schedule occurrence itself remains owned by SchedulerRuntime, so the same
        playlist is not restarted after each song completes.
        """
        playlist = PlaylistRepository(db).get_with_tracks(playlist_id)
        if playlist is None:
            raise QueueManagerError(f"No playlist with id {playlist_id}.")

        song_ids = [track.song_id for track in sorted(playlist.tracks, key=lambda t: (t.position, t.id))]
        if not song_ids:
            raise QueueEmptyError(f"Playlist {playlist_id} is empty; nothing to play.")

        repo = QueueRepository(db)
        current = self._current_playing(repo)
        if current is not None:
            current.status = QueueItemStatus.SKIPPED.value
            db.flush()

        repo.clear()
        items = repo.add_songs(song_ids)
        self._scheduled_playlist_active = True
        db.flush()

        result = self._start_item(db, items[0], source=PlaybackSource.SCHEDULE)
        if result is None:
            self._scheduled_playlist_active = False
            raise QueueEmptyError(f"Playlist {playlist_id} contains no playable tracks.")
        db.commit()
        return result

    @property
    def scheduled_playlist_active(self) -> bool:
        return self._scheduled_playlist_active

    # ------------------------------------------------------------------
    # Internal: engine event handling (fires on whatever thread the
    # engine/player call back on - synchronous within stop()/the
    # output's finished-callback, so we open our own short-lived DB
    # session rather than relying on a request-scoped one)
    # ------------------------------------------------------------------

    def _on_scheduled_track_end(self, reason: TrackEndReason) -> None:
        if not self._scheduled_playlist_active:
            return
        if reason == TrackEndReason.COMPLETED:
            try:
                with session_scope() as db:
                    self._advance_after_completion(db, source=PlaybackSource.SCHEDULE)
            except Exception:
                logger.exception("Scheduled playlist failed to advance after track completion")
        elif reason == TrackEndReason.MANUAL_STOP:
            try:
                with session_scope() as db:
                    self._mark_current_skipped(db)
            finally:
                self._scheduled_playlist_active = False

    def _on_scheduled_preempted(self, previous: PlaybackSource, new: PlaybackSource) -> None:
        if not self._scheduled_playlist_active:
            return
        try:
            with session_scope() as db:
                self._mark_current_skipped(db)
        except Exception:
            logger.exception("Failed to mark scheduled playlist item skipped on preemption")
        finally:
            self._scheduled_playlist_active = False

    def _on_track_end(self, reason: TrackEndReason) -> None:
        # In standalone/test mode the shared AudioEngine callback is used for
        # both ordinary queue playback and scheduled playlist playback.
        if self._scheduled_playlist_active:
            self._on_scheduled_track_end(reason)
            return
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

    def _advance_after_completion(self, db: Session, *, source: PlaybackSource = PlaybackSource.QUEUE) -> None:
        repo = QueueRepository(db)
        current = self._current_playing(repo)
        if current is not None:
            current.status = QueueItemStatus.PLAYED.value
            db.flush()

        next_item = self._first_queued(repo)
        if next_item is None:
            # Natural completion has already transitioned the deck/output to
            # STOPPED. Do not call stop() again from the audio callback; only
            # release playback ownership. This avoids re-entering PortAudio
            # during its completion callback.
            if self._controller is not None:
                self._controller.release_if_owned(source)
            if source == PlaybackSource.SCHEDULE:
                self._scheduled_playlist_active = False
            return

        self._start_item(db, next_item, source=source)

    def _on_preempted(
        self,
        previous: PlaybackSource,
        new: PlaybackSource,
    ) -> None:
        # Loading another source through AudioEngine does not emit
        # MANUAL_STOP. Persist the queue transition explicitly so a queue item
        # can never remain PLAYING after Scheduler/Manual playback takes over.
        try:
            with session_scope() as db:
                repo = QueueRepository(db)
                current = self._current_playing(repo)
                if current is not None:
                    current.status = QueueItemStatus.SKIPPED.value
                    db.flush()
        except Exception:
            logger.exception(
                "QueueManager failed to mark the current item SKIPPED on preemption."
            )

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

    def _start_item(self, db: Session, item: QueueItem, *, source: PlaybackSource = PlaybackSource.QUEUE) -> Optional[dict]:
        repo = QueueRepository(db)
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
            return self._advance_past_failure(db, source=source)

        try:
            next_file_path = None
            next_item = None
            if self._controller is not None:
                for candidate in repo.list_all():
                    if self._status(candidate) == QueueItemStatus.QUEUED and candidate.id != item.id:
                        candidate_song = song_repo.get_by_id(candidate.song_id)
                        if candidate_song is not None and candidate_song.enabled:
                            next_item = candidate
                            next_file_path = candidate_song.file_path
                            break

                status = self._controller.start_track(
                    source,
                    song.file_path,
                    next_file_path=next_file_path,
                    on_crossfade_complete=self._on_crossfade_complete if next_file_path else None,
                )
            else:
                self._engine.load_track(song.file_path)
                status = self._engine.play()
        except AudioEngineError as exc:

            logger.warning("Failed to play queue item %s (%s): %s", item.id, song.file_path, exc)
            item.status = QueueItemStatus.FAILED.value
            db.flush()
            return self._advance_past_failure(db, source=source)

        item.status = QueueItemStatus.PLAYING.value
        db.flush()
        song_repo.record_play(song.id)
        db.flush()
        return status.to_dict()


    def _on_crossfade_complete(self, old_file_path: str, new_file_path: str) -> None:
        """Persist a completed crossfade and immediately arm the following track."""
        if self._controller is None:
            return
        try:
            with session_scope() as db:
                repo = QueueRepository(db)
                song_repo = SongRepository(db)

                current = self._current_playing(repo)
                if current is not None:
                    current.status = QueueItemStatus.PLAYED.value
                    db.flush()

                next_item = None
                for candidate in repo.list_all():
                    if self._status(candidate) != QueueItemStatus.QUEUED:
                        continue
                    candidate_song = song_repo.get_by_id(candidate.song_id)
                    if candidate_song is not None and candidate_song.enabled and candidate_song.file_path == new_file_path:
                        next_item = candidate
                        break

                if next_item is None:
                    logger.warning("Crossfade target %r was not found in the queued database state", new_file_path)
                    self._controller.release_if_owned(PlaybackSource.SCHEDULE if self._scheduled_playlist_active else PlaybackSource.QUEUE)
                    return

                next_item.status = QueueItemStatus.PLAYING.value
                db.flush()
                song_repo.record_play(next_item.song_id)
                db.flush()

                following_file_path = None
                for candidate in repo.list_all():
                    if self._status(candidate) != QueueItemStatus.QUEUED:
                        continue
                    candidate_song = song_repo.get_by_id(candidate.song_id)
                    if candidate_song is not None and candidate_song.enabled:
                        following_file_path = candidate_song.file_path
                        break

                self._controller.set_next_track(
                    following_file_path,
                    self._on_crossfade_complete if following_file_path else None,
                )
        except Exception:
            logger.exception("QueueManager failed to persist crossfade completion")

    def _advance_past_failure(self, db: Session, *, source: PlaybackSource = PlaybackSource.QUEUE) -> Optional[dict]:
        repo = QueueRepository(db)
        next_item = self._first_queued(repo)
        if next_item is None:
            self._stop_cleanly(source)
            if source == PlaybackSource.SCHEDULE:
                self._scheduled_playlist_active = False
            return None
        return self._start_item(db, next_item, source=source)

    def _stop_cleanly(self, source: PlaybackSource = PlaybackSource.QUEUE) -> None:
        """Stop only queue-owned playback; never stop a higher-priority source."""
        try:
            if self._controller is not None:
                if self._controller.owns(source):
                    self._controller.stop(source)
                return
            self._engine.stop()
        except (AudioEngineError, PlaybackControllerError):
            logger.debug(
                "Queue playback was already stopped or is owned by another source."
            )

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
