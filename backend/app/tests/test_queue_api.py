"""
tests/test_queue_api.py
==========================

HTTP-level tests for the runtime Playback Queue API (V0.3) via
FastAPI's TestClient, plus regression checks that V0.2's Music
Library API and V0.3's Playlist API still work unmodified.

`app.main` can't be imported here: `app/api/playback.py` does
`from src.models import AudioEngineError`, and the V0.1 `src` package
(AudioEngine) isn't part of this uploaded bundle - a pre-existing gap
unrelated to the queue work (see `test_playlist_api.py`). So this
module builds a local FastAPI app wired up the same way `main.py`
does, minus `playback.router`, to test everything that's actually
present: `library.router`, `playlists.router`, and the new
`queue.router`.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import library, playlists, queue
from app.database import database as db_module
from app.database.database import get_db
from app.database.repositories.song_repository import SongRepository


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_module.reset_engine(f"sqlite:///{path}")

    app = FastAPI()
    app.include_router(library.router)
    app.include_router(playlists.router)
    app.include_router(queue.router)

    def _get_db_override():
        db = db_module.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_override

    with TestClient(app) as c:
        yield c

    os.remove(path)


def make_song(**overrides) -> int:
    """Insert a song directly via the repository and return its id."""
    db = db_module.SessionLocal()
    data = {
        "file_path": overrides.pop("file_path", "/music/default.mp3"),
        "file_name": "default.mp3",
        "title": "Default Title",
        "artist": "Default Artist",
        "album": "",
        "album_artist": "",
        "genre": "",
        "duration": 200.0,
        "file_size": 1234,
        "format": "mp3",
    }
    data.update(overrides)
    song, _ = SongRepository(db).upsert(data)
    db.commit()
    song_id = song.id
    db.close()
    return song_id


def add_to_queue(client, song_id, **kwargs):
    return client.post("/api/queue", json={"song_id": song_id, **kwargs})


# ----------------------------------------------------------------------
# V0.2 / V0.3 regressions
# ----------------------------------------------------------------------

def test_v02_library_api_still_works(client):
    song_id = make_song(title="Regression Song")
    resp = client.get("/api/library/songs")
    assert resp.status_code == 200
    assert any(s["id"] == song_id for s in resp.json())


def test_v03_playlist_api_still_works(client):
    resp = client.post("/api/playlists", json={"name": "Still Works"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Still Works"


# ----------------------------------------------------------------------
# Empty queue
# ----------------------------------------------------------------------

def test_get_empty_queue_returns_empty_list(client):
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    assert resp.json() == []


def test_clear_empty_queue_succeeds(client):
    resp = client.delete("/api/queue")
    assert resp.status_code == 204


def test_remove_from_empty_queue_returns_404(client):
    resp = client.delete("/api/queue/1")
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Add track
# ----------------------------------------------------------------------

def test_add_track_appends_and_returns_item_with_song(client):
    song_id = make_song(title="Add Me", file_path="/music/add.mp3")
    resp = add_to_queue(client, song_id)
    assert resp.status_code == 201
    body = resp.json()
    assert body["song_id"] == song_id
    assert body["position"] == 0
    assert body["status"] == "QUEUED"
    assert body["song"]["title"] == "Add Me"


def test_add_track_invalid_song_returns_404(client):
    resp = add_to_queue(client, 999999)
    assert resp.status_code == 404


def test_add_track_preserves_order_across_requests(client):
    ids = [make_song(title=f"S{i}", file_path=f"/music/order{i}.mp3") for i in range(3)]
    for sid in ids:
        add_to_queue(client, sid)

    resp = client.get("/api/queue")
    items = resp.json()
    assert [i["song_id"] for i in items] == ids
    assert [i["position"] for i in items] == [0, 1, 2]


def test_add_track_duplicate_song_creates_two_items(client):
    song_id = make_song(title="Dup", file_path="/music/dup.mp3")
    first = add_to_queue(client, song_id).json()
    second = add_to_queue(client, song_id).json()

    assert first["id"] != second["id"]
    items = client.get("/api/queue").json()
    assert len(items) == 2
    assert all(i["song_id"] == song_id for i in items)


def test_add_track_deleted_song_returns_404(client):
    """A song that used to exist but was hard-deleted from the library
    behaves the same as one that never existed."""
    song_id = make_song(title="To Delete", file_path="/music/todelete.mp3")
    client.delete(f"/api/library/songs/{song_id}")

    resp = add_to_queue(client, song_id)
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Play Next
# ----------------------------------------------------------------------

def test_play_next_inserts_ahead_of_existing_queue(client):
    first = make_song(title="First", file_path="/music/first.mp3")
    urgent = make_song(title="Urgent", file_path="/music/urgent.mp3")
    add_to_queue(client, first)

    resp = add_to_queue(client, urgent, play_next=True)
    assert resp.status_code == 201
    assert resp.json()["position"] == 0

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [urgent, first]


def test_multiple_play_next_operations_stack_most_recent_first(client):
    base = make_song(title="Base", file_path="/music/pnbase.mp3")
    a = make_song(title="PNA", file_path="/music/pna_api.mp3")
    b = make_song(title="PNB", file_path="/music/pnb_api.mp3")

    add_to_queue(client, base)
    add_to_queue(client, a, play_next=True)
    add_to_queue(client, b, play_next=True)

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [b, a, base]


# ----------------------------------------------------------------------
# Add playlist
# ----------------------------------------------------------------------

def test_add_playlist_appends_all_tracks_in_order(client):
    playlist_id = client.post("/api/playlists", json={"name": "Queue Me"}).json()["id"]
    ids = [make_song(title=f"P{i}", file_path=f"/music/plq{i}.mp3") for i in range(3)]
    for sid in ids:
        client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": sid})

    resp = client.post(f"/api/queue/playlist/{playlist_id}")
    assert resp.status_code == 201
    created = resp.json()
    assert [t["song_id"] for t in created] == ids

    queue_items = client.get("/api/queue").json()
    assert [i["song_id"] for i in queue_items] == ids
    assert [i["position"] for i in queue_items] == [0, 1, 2]


def test_add_playlist_appends_after_existing_queue_items(client):
    existing = make_song(title="Existing", file_path="/music/existingq.mp3")
    add_to_queue(client, existing)

    playlist_id = client.post("/api/playlists", json={"name": "Append Test"}).json()["id"]
    song_id = make_song(title="PlaylistSong", file_path="/music/plsong.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    client.post(f"/api/queue/playlist/{playlist_id}")

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [existing, song_id]


def test_add_playlist_invalid_playlist_returns_404(client):
    resp = client.post("/api/queue/playlist/999999")
    assert resp.status_code == 404


def test_add_empty_playlist_queues_nothing(client):
    playlist_id = client.post("/api/playlists", json={"name": "Empty"}).json()["id"]
    resp = client.post(f"/api/queue/playlist/{playlist_id}")
    assert resp.status_code == 201
    assert resp.json() == []
    assert client.get("/api/queue").json() == []


# ----------------------------------------------------------------------
# Remove track
# ----------------------------------------------------------------------

def test_remove_track_closes_gap(client):
    ids = [make_song(title=f"R{i}", file_path=f"/music/apirem{i}.mp3") for i in range(2)]
    item_ids = [add_to_queue(client, sid).json()["id"] for sid in ids]

    resp = client.delete(f"/api/queue/{item_ids[0]}")
    assert resp.status_code == 204

    items = client.get("/api/queue").json()
    assert len(items) == 1
    assert items[0]["song_id"] == ids[1]
    assert items[0]["position"] == 0


def test_remove_track_invalid_id_returns_404(client):
    resp = client.delete("/api/queue/999999")
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Move up / move down
# ----------------------------------------------------------------------

def test_move_track_up(client):
    ids = [make_song(title=f"M{i}", file_path=f"/music/apimv{i}.mp3") for i in range(3)]
    item_ids = [add_to_queue(client, sid).json()["id"] for sid in ids]

    resp = client.post(f"/api/queue/{item_ids[2]}/move-up")
    assert resp.status_code == 200

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [ids[0], ids[2], ids[1]]


def test_move_track_down(client):
    ids = [make_song(title=f"D{i}", file_path=f"/music/apidown{i}.mp3") for i in range(3)]
    item_ids = [add_to_queue(client, sid).json()["id"] for sid in ids]

    resp = client.post(f"/api/queue/{item_ids[0]}/move-down")
    assert resp.status_code == 200

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [ids[1], ids[0], ids[2]]


def test_move_up_first_item_is_a_no_op(client):
    song_id = make_song(title="Solo", file_path="/music/solo.mp3")
    item_id = add_to_queue(client, song_id).json()["id"]

    resp = client.post(f"/api/queue/{item_id}/move-up")
    assert resp.status_code == 200
    assert resp.json()["position"] == 0


def test_move_down_last_item_is_a_no_op(client):
    song_id = make_song(title="Solo2", file_path="/music/solo2.mp3")
    item_id = add_to_queue(client, song_id).json()["id"]

    resp = client.post(f"/api/queue/{item_id}/move-down")
    assert resp.status_code == 200
    assert resp.json()["position"] == 0


def test_move_up_invalid_id_returns_404(client):
    resp = client.post("/api/queue/999999/move-up")
    assert resp.status_code == 404


def test_move_down_invalid_id_returns_404(client):
    resp = client.post("/api/queue/999999/move-down")
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Full reorder
# ----------------------------------------------------------------------

def test_reorder_queue(client):
    ids = [make_song(title=f"O{i}", file_path=f"/music/apireorder{i}.mp3") for i in range(3)]
    item_ids = [add_to_queue(client, sid).json()["id"] for sid in ids]

    new_order = [item_ids[2], item_ids[0], item_ids[1]]
    resp = client.put("/api/queue/reorder", json={"queue_item_ids": new_order})
    assert resp.status_code == 200
    body = resp.json()
    assert [i["id"] for i in body] == new_order
    assert [i["position"] for i in body] == [0, 1, 2]


def test_reorder_bad_permutation_returns_400(client):
    song_id = make_song(file_path="/music/apibadreorder.mp3")
    add_to_queue(client, song_id)

    resp = client.put("/api/queue/reorder", json={"queue_item_ids": [999999]})
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# Clear queue
# ----------------------------------------------------------------------

def test_clear_queue(client):
    for i in range(3):
        sid = make_song(title=f"C{i}", file_path=f"/music/apiclear{i}.mp3")
        add_to_queue(client, sid)

    resp = client.delete("/api/queue")
    assert resp.status_code == 204
    assert client.get("/api/queue").json() == []


# ----------------------------------------------------------------------
# Deleted song
# ----------------------------------------------------------------------

def test_deleting_song_removes_it_from_the_queue(client):
    song_id = make_song(title="Doomed", file_path="/music/apidoomed.mp3")
    other_id = make_song(title="Survivor", file_path="/music/apisurvivor.mp3")
    add_to_queue(client, song_id)
    add_to_queue(client, other_id)

    resp = client.delete(f"/api/library/songs/{song_id}")
    assert resp.status_code == 204

    items = client.get("/api/queue").json()
    assert [i["song_id"] for i in items] == [other_id]


def test_queue_does_not_affect_playlists_or_library(client):
    """Queueing a song is purely additive bookkeeping - it must not
    touch the song row, its play count, or any playlist it's in."""
    playlist_id = client.post("/api/playlists", json={"name": "Untouched"}).json()["id"]
    song_id = make_song(title="Neutral", file_path="/music/neutral.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    add_to_queue(client, song_id)

    song = client.get(f"/api/library/songs/{song_id}").json()
    assert song["play_count"] == 0

    playlist = client.get(f"/api/playlists/{playlist_id}").json()
    assert playlist["track_count"] == 1
