"""
tests/test_queue_repository.py
=================================

Covers the V0.3 runtime Playback Queue at the repository/model level
(`QueueItem` + `QueueRepository`), against a real (temp-file) SQLite
database with foreign keys enabled, the same way the app runs in
production.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import inspect

from app.database import database as db_module
from app.database.models import QueueItem, QueueItemStatus, Song
from app.database.repositories.queue_repository import (
    QueueItemNotFoundError,
    QueueRepository,
    SongNotFoundError,
)
from app.database.repositories.song_repository import SongRepository


@pytest.fixture()
def session():
    """Fresh temp-file SQLite DB per test, FK enforcement included."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_module.reset_engine(f"sqlite:///{path}")
    s = db_module.SessionLocal()
    try:
        yield s
    finally:
        s.close()
        os.remove(path)


def make_song(db, **overrides) -> Song:
    data = {
        "file_path": overrides.pop("file_path", f"/music/{overrides.get('title', 'song')}.mp3"),
        "file_name": "song.mp3",
        "title": "Song",
        "artist": "Artist",
        "album": "",
        "album_artist": "",
        "genre": "",
        "duration": 180.0,
        "file_size": 1000,
        "format": "mp3",
    }
    data.update(overrides)
    song, _ = SongRepository(db).upsert(data)
    db.commit()
    return song


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------

def test_queue_items_table_exists(session):
    tables = inspect(session.bind).get_table_names()
    assert "queue_items" in tables


# ----------------------------------------------------------------------
# Get queue / empty queue
# ----------------------------------------------------------------------

def test_empty_queue_returns_empty_list(session):
    assert QueueRepository(session).list_all() == []


# ----------------------------------------------------------------------
# Add track
# ----------------------------------------------------------------------

def test_add_track_appends_to_end_with_dense_positions(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"S{i}", file_path=f"/music/add{i}.mp3") for i in range(3)]

    for song in songs:
        repo.add_track(song.id)
    session.commit()

    items = repo.list_all()
    assert [i.song_id for i in items] == [s.id for s in songs]
    assert [i.position for i in items] == [0, 1, 2]
    assert all(i.status == QueueItemStatus.QUEUED.value for i in items)
    assert all(i.added_at is not None for i in items)


def test_add_track_invalid_song_raises(session):
    repo = QueueRepository(session)
    with pytest.raises(SongNotFoundError):
        repo.add_track(999999)


def test_add_track_duplicate_song_creates_distinct_items(session):
    """The same song can be queued more than once - duplicates are
    allowed, and each becomes its own queue item."""
    repo = QueueRepository(session)
    song = make_song(session, title="Repeat", file_path="/music/repeat.mp3")

    first = repo.add_track(song.id)
    second = repo.add_track(song.id)
    session.commit()

    assert first.id != second.id
    items = repo.list_all()
    assert len(items) == 2
    assert [i.song_id for i in items] == [song.id, song.id]
    assert [i.position for i in items] == [0, 1]


# ----------------------------------------------------------------------
# Play Next
# ----------------------------------------------------------------------

def test_play_next_inserts_at_front_when_nothing_playing(session):
    repo = QueueRepository(session)
    a = make_song(session, title="A", file_path="/music/a.mp3")
    b = make_song(session, title="B", file_path="/music/b.mp3")
    repo.add_track(a.id)  # normal append -> position 0
    session.commit()

    item_b = repo.add_track(b.id, play_next=True)
    session.commit()

    items = repo.list_all()
    assert [i.song_id for i in items] == [b.id, a.id]
    assert item_b.position == 0


def test_play_next_inserts_after_currently_playing_item(session):
    repo = QueueRepository(session)
    now_playing = make_song(session, title="Playing", file_path="/music/playing.mp3")
    later = make_song(session, title="Later", file_path="/music/later.mp3")
    new_song = make_song(session, title="New", file_path="/music/new.mp3")

    playing_item = repo.add_track(now_playing.id)
    repo.add_track(later.id)
    session.commit()

    # Simulate the (future) engine integration marking an item PLAYING.
    playing_item.status = QueueItemStatus.PLAYING.value
    session.commit()

    repo.add_track(new_song.id, play_next=True)
    session.commit()

    items = repo.list_all()
    assert [i.song_id for i in items] == [now_playing.id, new_song.id, later.id]


def test_multiple_play_next_calls_stack_most_recent_first(session):
    """Repeated Play Next calls each insert right after the currently
    playing item, so the most recently requested track plays soonest -
    earlier Play Next requests get pushed back one slot each time."""
    repo = QueueRepository(session)
    base = make_song(session, title="Base", file_path="/music/base.mp3")
    a = make_song(session, title="PNA", file_path="/music/pna.mp3")
    b = make_song(session, title="PNB", file_path="/music/pnb.mp3")
    c = make_song(session, title="PNC", file_path="/music/pnc.mp3")

    repo.add_track(base.id)
    repo.add_track(a.id, play_next=True)
    repo.add_track(b.id, play_next=True)
    repo.add_track(c.id, play_next=True)
    session.commit()

    items = repo.list_all()
    assert [i.song_id for i in items] == [c.id, b.id, a.id, base.id]
    assert [i.position for i in items] == [0, 1, 2, 3]


# ----------------------------------------------------------------------
# Add playlist (song id list)
# ----------------------------------------------------------------------

def test_add_songs_preserves_order_and_appends(session):
    repo = QueueRepository(session)
    existing = make_song(session, title="Existing", file_path="/music/existing.mp3")
    repo.add_track(existing.id)
    session.commit()

    playlist_songs = [
        make_song(session, title=f"P{i}", file_path=f"/music/playlist{i}.mp3") for i in range(3)
    ]
    created = repo.add_songs([s.id for s in playlist_songs])
    session.commit()

    assert [i.song_id for i in created] == [s.id for s in playlist_songs]
    items = repo.list_all()
    assert [i.song_id for i in items] == [existing.id] + [s.id for s in playlist_songs]
    assert [i.position for i in items] == [0, 1, 2, 3]


def test_add_songs_with_empty_list_is_a_no_op(session):
    repo = QueueRepository(session)
    created = repo.add_songs([])
    session.commit()
    assert created == []
    assert repo.list_all() == []


# ----------------------------------------------------------------------
# Remove track
# ----------------------------------------------------------------------

def test_remove_track_closes_position_gap(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"R{i}", file_path=f"/music/rem{i}.mp3") for i in range(3)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    removed = repo.remove_track(items[1].id)
    session.commit()

    assert removed is True
    remaining = repo.list_all()
    assert [i.song_id for i in remaining] == [songs[0].id, songs[2].id]
    assert [i.position for i in remaining] == [0, 1]


def test_remove_track_missing_id_returns_false(session):
    repo = QueueRepository(session)
    assert repo.remove_track(999999) is False


def test_remove_track_from_empty_queue_returns_false(session):
    repo = QueueRepository(session)
    assert repo.remove_track(1) is False


# ----------------------------------------------------------------------
# Move up / move down
# ----------------------------------------------------------------------

def test_move_up_swaps_with_predecessor(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"M{i}", file_path=f"/music/mv{i}.mp3") for i in range(3)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    repo.move_up(items[2].id)
    session.commit()

    ordered = repo.list_all()
    assert [i.song_id for i in ordered] == [songs[0].id, songs[2].id, songs[1].id]


def test_move_up_on_first_item_is_a_no_op(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"F{i}", file_path=f"/music/first{i}.mp3") for i in range(2)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    result = repo.move_up(items[0].id)
    session.commit()

    assert result.position == 0
    assert [i.song_id for i in repo.list_all()] == [songs[0].id, songs[1].id]


def test_move_down_swaps_with_successor(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"D{i}", file_path=f"/music/down{i}.mp3") for i in range(3)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    repo.move_down(items[0].id)
    session.commit()

    ordered = repo.list_all()
    assert [i.song_id for i in ordered] == [songs[1].id, songs[0].id, songs[2].id]


def test_move_down_on_last_item_is_a_no_op(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"L{i}", file_path=f"/music/last{i}.mp3") for i in range(2)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    result = repo.move_down(items[1].id)
    session.commit()

    assert result.position == 1
    assert [i.song_id for i in repo.list_all()] == [songs[0].id, songs[1].id]


def test_move_up_missing_id_raises(session):
    repo = QueueRepository(session)
    with pytest.raises(QueueItemNotFoundError):
        repo.move_up(999999)


def test_move_down_missing_id_raises(session):
    repo = QueueRepository(session)
    with pytest.raises(QueueItemNotFoundError):
        repo.move_down(999999)


# ----------------------------------------------------------------------
# Reorder (full permutation)
# ----------------------------------------------------------------------

def test_reorder_applies_full_permutation(session):
    repo = QueueRepository(session)
    songs = [make_song(session, title=f"O{i}", file_path=f"/music/reord{i}.mp3") for i in range(3)]
    items = [repo.add_track(s.id) for s in songs]
    session.commit()

    new_order = [items[2].id, items[0].id, items[1].id]
    reordered = repo.reorder(new_order)
    session.commit()

    assert [i.id for i in reordered] == new_order
    assert [i.position for i in reordered] == [0, 1, 2]


def test_reorder_bad_permutation_raises(session):
    repo = QueueRepository(session)
    song = make_song(session, file_path="/music/badreorder.mp3")
    repo.add_track(song.id)
    session.commit()

    with pytest.raises(ValueError):
        repo.reorder([999999])


# ----------------------------------------------------------------------
# Clear queue
# ----------------------------------------------------------------------

def test_clear_removes_everything(session):
    repo = QueueRepository(session)
    for i in range(3):
        song = make_song(session, title=f"C{i}", file_path=f"/music/clear{i}.mp3")
        repo.add_track(song.id)
    session.commit()

    count = repo.clear()
    session.commit()

    assert count == 3
    assert repo.list_all() == []


def test_clear_empty_queue_returns_zero(session):
    repo = QueueRepository(session)
    assert repo.clear() == 0


# ----------------------------------------------------------------------
# Deleted song / invalid song references
# ----------------------------------------------------------------------

def test_deleting_song_removes_it_from_the_queue(session):
    """Hard-deleting a song from the library must cascade to the
    queue, the same way it already does for playlist_tracks."""
    repo = QueueRepository(session)
    song = make_song(session, title="Doomed", file_path="/music/doomed.mp3")
    other = make_song(session, title="Survivor", file_path="/music/survivor.mp3")
    repo.add_track(song.id)
    repo.add_track(other.id)
    session.commit()

    SongRepository(session).delete(song.id)
    session.commit()

    items = repo.list_all()
    assert [i.song_id for i in items] == [other.id]


def test_foreign_keys_enforced_at_db_level_for_queue_items(session):
    """A queue_items row can't reference a nonexistent song at the DB
    layer, independent of the repository's own up-front check."""
    from sqlalchemy.exc import IntegrityError

    bad_item = QueueItem(song_id=999999, position=0, status=QueueItemStatus.QUEUED.value)
    session.add(bad_item)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
