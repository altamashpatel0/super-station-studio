"""
app/database/repositories/queue_repository.py
================================================

All SQL/ORM operations on `queue_items` (the runtime Playback Queue,
V0.3) live here, mirroring `playlist_repository.py`. There is exactly
one queue for the whole application - a single, globally-ordered list
of songs pulled from the Music Library that represents "what's up
next" for the (existing, unmodified) V0.1 `AudioEngine`.

This module knows nothing about the audio engine itself and never
touches playback - it only manages which songs are queued and in what
order. It never copies or moves audio files; every queue item is just
a reference to an existing `songs.id`.

Order is maintained as a dense, zero-based `position` sequence over
the *entire* queue and is entirely owned by this repository - exactly
like `PlaylistRepository` owns `playlist_tracks.position`. `position`
is never taken as-is from a caller and written straight through.
"""

from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Asset, QueueItem, QueueItemStatus, Song


class SongNotFoundError(Exception):
    """Raised when an operation references a song id that doesn't exist."""


class QueueItemNotFoundError(Exception):
    """Raised when an operation references a queue_item id that doesn't exist."""


class QueueRepository:
    """Thin data-access layer around the single global `queue_items` list."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_all(self) -> Sequence[QueueItem]:
        stmt = (
            select(QueueItem)
            .order_by(QueueItem.position.asc())
            .options(selectinload(QueueItem.song), selectinload(QueueItem.asset))
        )
        return self.db.execute(stmt).scalars().all()

    def get_by_id(self, queue_item_id: int) -> Optional[QueueItem]:
        return self.db.get(QueueItem, queue_item_id)

    # ------------------------------------------------------------------
    # Adding
    # ------------------------------------------------------------------

    def add_track(self, song_id: int, *, play_next: bool = False) -> QueueItem:
        """
        Queue `song_id`, appended to the end by default.

        If `play_next` is set, the item is instead inserted immediately
        after whatever is currently `PLAYING` (or at the very front of
        the queue, if nothing currently is), bumping everything from
        that point on back by one slot.

        The same song may be queued any number of times - including
        while it's already sitting in the queue - each call always
        creates its own, distinct queue item; duplicates are never
        merged or rejected.

        Calling this with `play_next=True` more than once in a row
        stacks each new item right after the current `PLAYING` item, so
        the *most recently* requested "Play Next" track ends up
        soonest; earlier "Play Next" requests get pushed back one slot
        every time a new one comes in.

        Raises `SongNotFoundError` if `song_id` doesn't reference an
        existing library song.
        """
        if self.db.get(Song, song_id) is None:
            raise SongNotFoundError(f"No song with id {song_id}.")

        existing = list(self.list_all())
        insert_at = self._play_next_insert_index(existing) if play_next else len(existing)

        for item in existing[insert_at:]:
            item.position += 1

        item = QueueItem(
            song_id=song_id,
            position=insert_at,
            status=QueueItemStatus.QUEUED.value,
            added_at=datetime.datetime.utcnow(),
        )
        self.db.add(item)
        self.db.flush()
        return item

    def add_asset(self, asset_id: int, *, play_next: bool = False) -> QueueItem:
        """Queue one station asset (currently used for Promos)."""
        if self.db.get(Asset, asset_id) is None:
            raise ValueError(f"No asset with id {asset_id}.")
        existing = list(self.list_all())
        insert_at = self._play_next_insert_index(existing) if play_next else len(existing)
        for item in existing[insert_at:]:
            item.position += 1
        item = QueueItem(
            song_id=None,
            asset_id=asset_id,
            position=insert_at,
            status=QueueItemStatus.QUEUED.value,
            added_at=datetime.datetime.utcnow(),
        )
        self.db.add(item)
        self.db.flush()
        return item

    def add_playlist_items(self, track_refs: Sequence[dict]) -> list[QueueItem]:
        """Append playlist occurrences in order; each ref is {song_id} or {asset_id}."""
        start = len(self.list_all())
        created: list[QueueItem] = []
        now = datetime.datetime.utcnow()
        for offset, ref in enumerate(track_refs):
            song_id = ref.get("song_id")
            asset_id = ref.get("asset_id")
            if (song_id is None) == (asset_id is None):
                raise ValueError("Each playlist queue item must reference exactly one song or asset.")
            if song_id is not None and self.db.get(Song, song_id) is None:
                raise SongNotFoundError(f"No song with id {song_id}.")
            if asset_id is not None and self.db.get(Asset, asset_id) is None:
                raise ValueError(f"No asset with id {asset_id}.")
            item = QueueItem(
                song_id=song_id,
                asset_id=asset_id,
                position=start + offset,
                status=QueueItemStatus.QUEUED.value,
                added_at=now,
            )
            self.db.add(item)
            created.append(item)
        self.db.flush()
        return created

    def add_songs(self, song_ids: Sequence[int]) -> list[QueueItem]:
        """
        Append `song_ids` (already in the caller's desired order - e.g.
        a playlist's track order) to the end of the queue, preserving
        that order. Every id becomes its own queue item, including
        repeats, same as `add_track`. Callers are responsible for
        validating that every id in `song_ids` references an existing
        song (see `api/queue.py::add_playlist`, which draws them from a
        real playlist and therefore never passes an invalid one).
        """
        start = len(self.list_all())
        created: list[QueueItem] = []
        now = datetime.datetime.utcnow()
        for offset, song_id in enumerate(song_ids):
            item = QueueItem(
                song_id=song_id,
                position=start + offset,
                status=QueueItemStatus.QUEUED.value,
                added_at=now,
            )
            self.db.add(item)
            created.append(item)
        self.db.flush()
        return created

    # ------------------------------------------------------------------
    # Removing / clearing
    # ------------------------------------------------------------------

    def remove_track(self, queue_item_id: int) -> bool:
        """Remove one queue item and close the resulting gap in positions."""
        item = self.get_by_id(queue_item_id)
        if item is None:
            return False

        removed_position = item.position
        self.db.delete(item)
        self.db.flush()

        for remaining in self.list_all():
            if remaining.position > removed_position:
                remaining.position -= 1
        self.db.flush()
        return True

    def clear(self) -> int:
        """Remove every item from the queue. Returns the number removed."""
        items = self.list_all()
        count = len(items)
        for item in items:
            self.db.delete(item)
        self.db.flush()
        return count

    # ------------------------------------------------------------------
    # Reordering
    # ------------------------------------------------------------------

    def move_up(self, queue_item_id: int) -> QueueItem:
        """Swap a queue item with its predecessor. No-op if it's already first."""
        item = self.get_by_id(queue_item_id)
        if item is None:
            raise QueueItemNotFoundError(f"No queue item with id {queue_item_id}.")
        if item.position == 0:
            return item
        neighbor = self._at_position(item.position - 1)
        if neighbor is not None:
            neighbor.position, item.position = item.position, neighbor.position
        self.db.flush()
        return item

    def move_down(self, queue_item_id: int) -> QueueItem:
        """Swap a queue item with its successor. No-op if it's already last."""
        item = self.get_by_id(queue_item_id)
        if item is None:
            raise QueueItemNotFoundError(f"No queue item with id {queue_item_id}.")
        last_position = len(self.list_all()) - 1
        if item.position >= last_position:
            return item
        neighbor = self._at_position(item.position + 1)
        if neighbor is not None:
            neighbor.position, item.position = item.position, neighbor.position
        self.db.flush()
        return item

    def reorder(self, ordered_queue_item_ids: list[int]) -> Sequence[QueueItem]:
        """
        Re-sequence the whole queue to match `ordered_queue_item_ids`
        exactly. It must be a permutation of the queue's current
        `queue_items.id` values.
        """
        current = list(self.list_all())
        current_ids = {i.id for i in current}
        if len(ordered_queue_item_ids) != len(current) or set(ordered_queue_item_ids) != current_ids:
            raise ValueError(
                "ordered_queue_item_ids must be a permutation of the queue's current item ids."
            )

        by_id = {i.id: i for i in current}
        for index, item_id in enumerate(ordered_queue_item_ids):
            by_id[item_id].position = index
        self.db.flush()
        return self.list_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _at_position(self, position: int) -> Optional[QueueItem]:
        for item in self.list_all():
            if item.position == position:
                return item
        return None

    @staticmethod
    def _play_next_insert_index(items: Sequence[QueueItem]) -> int:
        for item in items:
            status = item.status.value if isinstance(item.status, QueueItemStatus) else item.status
            if status == QueueItemStatus.PLAYING.value:
                return item.position + 1
        return 0
