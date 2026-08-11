"""tests/test_database.py — DB init + SongRepository CRUD."""

from __future__ import annotations

from app.database.repositories.song_repository import SongRepository


def _sample_data(**overrides) -> dict:
    data = {
        "file_path": "/music/tum_hi_ho.mp3",
        "file_name": "tum_hi_ho.mp3",
        "title": "Tum Hi Ho",
        "artist": "Arijit Singh",
        "album": "Aashiqui 2",
        "album_artist": "Arijit Singh",
        "genre": "Bollywood",
        "year": 2013,
        "track_number": 1,
        "duration": 262.5,
        "sample_rate": 44100,
        "bitrate": 128,
        "file_size": 4_200_000,
        "format": "MP3",
    }
    data.update(overrides)
    return data


def test_database_initializes_songs_table(db_session):
    # db_session fixture already calls init_db() via reset_engine; a
    # trivial query should succeed against an empty table.
    repo = SongRepository(db_session)
    assert repo.list_all() == []


def test_add_song(db_session):
    repo = SongRepository(db_session)
    song, created = repo.upsert(_sample_data())
    db_session.commit()

    assert created is True
    assert song.id is not None
    assert song.title == "Tum Hi Ho"
    assert song.enabled is True


def test_retrieve_song_by_id_and_path(db_session):
    repo = SongRepository(db_session)
    song, _ = repo.upsert(_sample_data())
    db_session.commit()

    by_id = repo.get_by_id(song.id)
    by_path = repo.get_by_path("/music/tum_hi_ho.mp3")

    assert by_id is not None and by_id.id == song.id
    assert by_path is not None and by_path.id == song.id
    assert repo.get_by_id(99999) is None
    assert repo.get_by_path("/does/not/exist.mp3") is None


def test_update_song_via_upsert(db_session):
    repo = SongRepository(db_session)
    song, created = repo.upsert(_sample_data())
    db_session.commit()
    assert created is True
    original_id = song.id

    updated, created_again = repo.upsert(_sample_data(album="Deluxe Edition", play_count=0))
    db_session.commit()

    assert created_again is False
    assert updated.id == original_id  # same row, not a duplicate
    assert updated.album == "Deluxe Edition"
    assert repo.list_all().__len__() == 1


def test_disable_song(db_session):
    repo = SongRepository(db_session)
    song, _ = repo.upsert(_sample_data())
    db_session.commit()

    result = repo.set_enabled(song.id, False)
    db_session.commit()

    assert result.enabled is False
    assert repo.get_by_id(song.id).enabled is False
    # Soft-disable retains the row (and any play history) rather than deleting it.
    assert len(repo.list_all()) == 1


def test_delete_song(db_session):
    repo = SongRepository(db_session)
    song, _ = repo.upsert(_sample_data())
    db_session.commit()

    assert repo.delete(song.id) is True
    db_session.commit()
    assert repo.get_by_id(song.id) is None
    assert repo.delete(song.id) is False  # already gone


def test_record_play_increments_count_and_timestamp(db_session):
    repo = SongRepository(db_session)
    song, _ = repo.upsert(_sample_data())
    db_session.commit()
    assert song.play_count == 0
    assert song.last_played is None

    repo.record_play(song.id)
    db_session.commit()

    refreshed = repo.get_by_id(song.id)
    assert refreshed.play_count == 1
    assert refreshed.last_played is not None


def test_file_path_is_unique_key(db_session):
    """Two upserts with the same file_path must never produce two rows,
    even if every other field differs (e.g. re-tagged file)."""
    repo = SongRepository(db_session)
    repo.upsert(_sample_data(title="Old Title"))
    db_session.commit()
    repo.upsert(_sample_data(title="New Title"))
    db_session.commit()

    all_songs = repo.list_all()
    assert len(all_songs) == 1
    assert all_songs[0].title == "New Title"
