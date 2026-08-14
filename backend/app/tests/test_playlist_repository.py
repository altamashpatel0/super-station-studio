"""
tests/test_playlist_repository.py
====================================

Covers the V0.3 Playlist database foundation (models + repository),
plus a regression check that V0.2's SongRepository/schema are
untouched by the change.

No test suite shipped with the uploaded V0.1/V0.2 bundle to run
as-is (only the `app/` package was present, and `app/api/playback.py`
depends on the V0.1 `src.AudioEngine` package, which isn't included
here either) - this file is written fresh to exercise both the
pre-existing `songs` table behavior and the new playlist behavior
against a real (temp-file) SQLite database with foreign keys enabled,
the same way the app runs in production.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import inspect

from app.database import database as db_module
from app.database.models import PlaylistTrack, Song
from app.database.repositories.playlist_repository import (
    PlaylistNotFoundError,
    PlaylistRepository,
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

def test_schema_has_expected_tables_and_v02_table_intact(session):
    inspector = inspect(session.get_bind())
    tables = set(inspector.get_table_names())

    assert {"songs", "scanned_folders", "playlists", "playlist_tracks"} <= tables

    song_cols = {c["name"] for c in inspector.get_columns("songs")}
    assert song_cols == {
        "id", "file_path", "file_name", "title", "artist", "album", "album_artist",
        "genre", "year", "track_number", "duration", "sample_rate", "bitrate",
        "file_size", "format", "date_added", "last_modified", "last_played",
        "play_count", "enabled",
    }

    playlist_cols = {c["name"] for c in inspector.get_columns("playlists")}
    assert playlist_cols == {"id", "name", "description", "created_at", "updated_at"}

    pt_cols = {c["name"] for c in inspector.get_columns("playlist_tracks")}
    assert pt_cols == {"id", "playlist_id", "song_id", "position", "added_at"}

    fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("playlist_tracks")}
    assert fks == {"playlists", "songs"}


# ----------------------------------------------------------------------
# V0.2 regression: SongRepository untouched
# ----------------------------------------------------------------------

def test_v02_song_repository_still_works(session):
    repo = SongRepository(session)
    song, created = repo.upsert(
        {
            "file_path": "/music/a.mp3",
            "file_name": "a.mp3",
            "title": "A",
            "artist": "Artist",
            "album": "",
            "album_artist": "",
            "genre": "",
            "duration": 120.0,
            "file_size": 500,
            "format": "mp3",
        }
    )
    session.commit()
    assert created is True
    assert repo.get_by_path("/music/a.mp3").id == song.id
    assert repo.stats()["total_songs"] == 1


# ----------------------------------------------------------------------
# Playlist CRUD
# ----------------------------------------------------------------------

def test_create_get_update_delete_playlist(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("Chill Vibes", "For late nights")
    session.commit()

    assert playlist.id is not None
    assert playlist.created_at == playlist.updated_at

    fetched = repo.get_by_id(playlist.id)
    assert fetched.name == "Chill Vibes"

    updated = repo.update(playlist.id, name="Chill Vibes 2.0")
    session.commit()
    assert updated.name == "Chill Vibes 2.0"
    assert updated.description == "For late nights"  # unchanged
    assert updated.updated_at >= updated.created_at

    assert repo.delete(playlist.id) is True
    assert repo.get_by_id(playlist.id) is None
    assert repo.delete(playlist.id) is False  # already gone


def test_update_nonexistent_playlist_raises(session):
    repo = PlaylistRepository(session)
    with pytest.raises(PlaylistNotFoundError):
        repo.update(999, name="Nope")


# ----------------------------------------------------------------------
# Track membership: many-to-many + order preservation
# ----------------------------------------------------------------------

def test_add_track_appends_and_preserves_order(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    songs = [make_song(session, title=f"S{i}", file_path=f"/music/s{i}.mp3") for i in range(3)]

    for s in songs:
        repo.add_track(playlist.id, s.id)
    session.commit()

    tracks = repo.list_tracks(playlist.id)
    assert [t.song_id for t in tracks] == [s.id for s in songs]
    assert [t.position for t in tracks] == [0, 1, 2]


def test_add_track_at_specific_position_shifts_others(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    a = make_song(session, title="A", file_path="/music/a.mp3")
    b = make_song(session, title="B", file_path="/music/b.mp3")
    c = make_song(session, title="C", file_path="/music/c.mp3")

    repo.add_track(playlist.id, a.id)  # position 0
    repo.add_track(playlist.id, b.id)  # position 1
    repo.add_track(playlist.id, c.id, position=1)  # insert between a and b
    session.commit()

    tracks = repo.list_tracks(playlist.id)
    assert [t.song_id for t in tracks] == [a.id, c.id, b.id]
    assert [t.position for t in tracks] == [0, 1, 2]


def test_same_song_can_be_added_to_multiple_playlists_and_repeated(session):
    repo = PlaylistRepository(session)
    p1 = repo.create("Playlist 1")
    p2 = repo.create("Playlist 2")
    song = make_song(session)

    repo.add_track(p1.id, song.id)
    repo.add_track(p2.id, song.id)
    repo.add_track(p1.id, song.id)  # duplicate within the same playlist is allowed
    session.commit()

    assert len(repo.list_tracks(p1.id)) == 2
    assert len(repo.list_tracks(p2.id)) == 1


def test_remove_track_closes_gap(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    songs = [make_song(session, title=f"S{i}", file_path=f"/music/g{i}.mp3") for i in range(3)]
    ids = [repo.add_track(playlist.id, s.id).id for s in songs]
    session.commit()

    assert repo.remove_track(playlist.id, ids[1]) is True  # remove the middle one
    session.commit()

    tracks = repo.list_tracks(playlist.id)
    assert [t.song_id for t in tracks] == [songs[0].id, songs[2].id]
    assert [t.position for t in tracks] == [0, 1]


def test_reorder_tracks(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    songs = [make_song(session, title=f"S{i}", file_path=f"/music/r{i}.mp3") for i in range(3)]
    tracks = [repo.add_track(playlist.id, s.id) for s in songs]
    session.commit()
    track_ids = [t.id for t in tracks]

    new_order = [track_ids[2], track_ids[0], track_ids[1]]
    reordered = repo.reorder_tracks(playlist.id, new_order)
    session.commit()

    assert [t.id for t in reordered] == new_order
    assert [t.position for t in reordered] == [0, 1, 2]


def test_reorder_tracks_rejects_non_permutation(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    song = make_song(session)
    repo.add_track(playlist.id, song.id)
    session.commit()

    with pytest.raises(ValueError):
        repo.reorder_tracks(playlist.id, [12345])


# ----------------------------------------------------------------------
# Invalid references
# ----------------------------------------------------------------------

def test_add_track_to_nonexistent_playlist_raises(session):
    repo = PlaylistRepository(session)
    song = make_song(session)
    with pytest.raises(PlaylistNotFoundError):
        repo.add_track(999, song.id)


def test_add_nonexistent_song_raises(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("My Mix")
    with pytest.raises(SongNotFoundError):
        repo.add_track(playlist.id, 999)


def test_foreign_keys_enforced_at_db_level(session):
    """Bypass the repository and attempt a raw invalid insert - the DB
    itself (not just app-level checks) must reject it."""
    bad = PlaylistTrack(playlist_id=999, song_id=999, position=0)
    session.add(bad)
    with pytest.raises(Exception):
        session.flush()
    session.rollback()


def test_deleting_playlist_cascades_to_tracks(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("Temp")
    song = make_song(session)
    repo.add_track(playlist.id, song.id)
    session.commit()

    playlist_id = playlist.id
    repo.delete(playlist_id)
    session.commit()

    remaining = session.query(PlaylistTrack).filter_by(playlist_id=playlist_id).all()
    assert remaining == []


def test_deleting_song_cascades_to_playlist_tracks(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("Keep Me")
    song = make_song(session)
    repo.add_track(playlist.id, song.id)
    session.commit()

    SongRepository(session).delete(song.id)
    session.commit()

    # Playlist itself survives; the dangling track row is gone.
    assert repo.get_by_id(playlist.id) is not None
    assert repo.list_tracks(playlist.id) == []


def test_get_with_tracks_eager_loads_songs(session):
    repo = PlaylistRepository(session)
    playlist = repo.create("Eager")
    song = make_song(session, title="Eager Song")
    repo.add_track(playlist.id, song.id)
    session.commit()
    session.expire_all()

    fetched = repo.get_with_tracks(playlist.id)
    assert fetched.tracks[0].song.title == "Eager Song"

    d = fetched.to_dict(include_tracks=True)
    assert d["track_count"] == 1
    assert d["tracks"][0]["song"]["title"] == "Eager Song"
