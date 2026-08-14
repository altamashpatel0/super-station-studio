"""
queue_source.py
================

`QueueCrossfadeManager` (see `queue_crossfade_manager.py`) needs to
walk "current track / next track / advance past a finished track /
skip a broken track" without caring whether that queue is backed by
the V0.3 SQLAlchemy `QueueRepository` (used by the FastAPI app) or
something simpler.

`QueueSource` is that minimal seam: four read/mutate operations, none
of which know anything about decks, crossfading, or audio at all -
exactly the same "thin adapter, no duplicated logic" shape as
`Deck`/`TwoDeckEngine` already use for `AudioEngine`.

`InMemoryQueueSource` is a real, fully-functional implementation used
directly by any non-FastAPI caller (and by the test suite, in place of
a database). Wiring a `QueueSource` on top of the existing
`QueueRepository` (V0.3) for the FastAPI app is a small adapter that
calls the repository's existing `list_all()` and status-updating
methods - no changes to `QueueRepository`/`QueueItem` are required;
see `QueueRepositorySource` below for exactly that adapter, kept
optional (imported lazily) so this module has no hard dependency on
the database layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol, Set


@dataclass(frozen=True)
class QueueTrack:
    """The minimal shape `QueueCrossfadeManager` needs for a queued
    track: something to identify it, and a file path `Deck.load_track`
    can use directly."""

    id: Any
    file_path: str


class QueueSource(Protocol):
    """Everything `QueueCrossfadeManager` needs from a queue."""

    def current(self) -> Optional[QueueTrack]:
        """The track that is (or should be) playing right now, or None
        if the queue has nothing playable left."""
        ...

    def peek_next(self) -> Optional[QueueTrack]:
        """The track that should play after `current()`, without
        consuming/advancing anything, or None if there isn't one."""
        ...

    def advance(self) -> Optional[QueueTrack]:
        """`current()` has finished (naturally, or via a completed
        crossfade) - move the pointer forward one track and return the
        new `current()` (None if the queue is now empty)."""
        ...

    def skip_next(self) -> Optional[QueueTrack]:
        """The track returned by `peek_next()` turned out to be
        unplayable (missing/corrupt file) - drop it without touching
        `current()`, and return the new `peek_next()`."""
        ...

    def skip_current(self) -> Optional[QueueTrack]:
        """`current()` itself turned out to be unplayable - drop it and
        return the new `current()` (None if the queue is now empty)."""
        ...


class InMemoryQueueSource:
    """A simple, in-memory `QueueSource` over an ordered list of
    tracks. Suitable for direct (non-FastAPI) use of
    `QueueCrossfadeManager`, and used throughout the test suite in
    place of a real database-backed queue."""

    def __init__(self, tracks: Optional[List[QueueTrack]] = None) -> None:
        self._tracks: List[QueueTrack] = list(tracks or [])
        self._pos = 0
        self._failed: Set[Any] = set()

    # -- mutation from outside (mirrors QueueRepository.add_track etc.) --

    def append(self, track: QueueTrack) -> None:
        self._tracks.append(track)

    # -- QueueSource protocol -------------------------------------------------

    def current(self) -> Optional[QueueTrack]:
        return self._at(self._pos)

    def peek_next(self) -> Optional[QueueTrack]:
        return self._at(self._next_valid_index(self._pos + 1))

    def advance(self) -> Optional[QueueTrack]:
        self._pos = self._next_valid_index(self._pos + 1)
        return self.current()

    def skip_next(self) -> Optional[QueueTrack]:
        idx = self._next_valid_index(self._pos + 1)
        track = self._at(idx)
        if track is not None:
            self._failed.add(track.id)
        return self.peek_next()

    def skip_current(self) -> Optional[QueueTrack]:
        track = self.current()
        if track is not None:
            self._failed.add(track.id)
        self._pos = self._next_valid_index(self._pos)
        return self.current()

    # -- internal --------------------------------------------------------

    def _at(self, index: int) -> Optional[QueueTrack]:
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    def _next_valid_index(self, start: int) -> int:
        idx = start
        while idx < len(self._tracks) and self._tracks[idx].id in self._failed:
            idx += 1
        return idx


class QueueRepositorySource:
    """Optional adapter over the V0.3 `QueueRepository` (FastAPI app),
    so `QueueCrossfadeManager` can drive the real, database-backed
    queue without any changes to `QueueRepository`/`QueueItem`.

    Only imported/instantiated by callers that actually have the
    FastAPI app's database layer available - this module itself does
    not import SQLAlchemy or the `app` package.
    """

    def __init__(self, db, queue_repository_cls=None, song_repository_cls=None) -> None:
        if queue_repository_cls is None or song_repository_cls is None:
            from app.database.repositories.queue_repository import QueueRepository
            from app.database.repositories.song_repository import SongRepository

            queue_repository_cls = queue_repository_cls or QueueRepository
            song_repository_cls = song_repository_cls or SongRepository

        self._db = db
        self._queue_repo = queue_repository_cls(db)
        self._song_repo = song_repository_cls(db)

    def _queued_items(self):
        from app.database.models import QueueItemStatus

        return [
            item
            for item in self._queue_repo.list_all()
            if self._status(item) == QueueItemStatus.QUEUED
        ]

    @staticmethod
    def _status(item):
        from app.database.models import QueueItemStatus

        return item.status if isinstance(item.status, QueueItemStatus) else QueueItemStatus(item.status)

    def _to_track(self, item) -> Optional[QueueTrack]:
        song = self._song_repo.get_by_id(item.song_id)
        if song is None or not song.enabled:
            return None
        return QueueTrack(id=item.id, file_path=song.file_path)

    def current(self) -> Optional[QueueTrack]:
        items = self._queued_items()
        return self._to_track(items[0]) if items else None

    def peek_next(self) -> Optional[QueueTrack]:
        items = self._queued_items()
        return self._to_track(items[1]) if len(items) > 1 else None

    def advance(self) -> Optional[QueueTrack]:
        from app.database.models import QueueItemStatus

        items = self._queued_items()
        if items:
            items[0].status = QueueItemStatus.PLAYED.value
            self._db.flush()
        return self.current()

    def skip_next(self) -> Optional[QueueTrack]:
        from app.database.models import QueueItemStatus

        items = self._queued_items()
        if len(items) > 1:
            items[1].status = QueueItemStatus.FAILED.value
            self._db.flush()
        return self.peek_next()

    def skip_current(self) -> Optional[QueueTrack]:
        from app.database.models import QueueItemStatus

        items = self._queued_items()
        if items:
            items[0].status = QueueItemStatus.FAILED.value
            self._db.flush()
        return self.current()
