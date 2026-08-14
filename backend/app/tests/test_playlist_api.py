"""
tests/test_playlist_api.py
=============================

HTTP-level tests for the Playlist API (V0.3) via FastAPI's TestClient,
plus a regression check that the V0.2 Music Library API still works
unmodified.

`app.main` can't be imported here: `app/api/playback.py` (V0.2) does
`from src.models import AudioEngineError`, and the V0.1 `src`
package (AudioEngine) was never part of this uploaded bundle - it's a
pre-existing gap unrelated to the V0.3 playlist work. So this module
builds a local FastAPI app wired up the same way `main.py` does,
minus `playback.router`, to test everything that's actually present:
`library.router` and the new `playlists.router`.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import library, playlists
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


# ----------------------------------------------------------------------
# V0.2 Music Library API regression
# ----------------------------------------------------------------------

def test_v02_library_api_still_works(client):
    song_id = make_song(title="Regression Song")
    resp = client.get("/api/library/songs")
    assert resp.status_code == 200
    assert any(s["id"] == song_id for s in resp.json())

    resp = client.get(f"/api/library/songs/{song_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Regression Song"

    resp = client.get("/api/library/stats")
    assert resp.status_code == 200
    assert resp.json()["total_songs"] == 1


# ----------------------------------------------------------------------
# Playlist CRUD
# ----------------------------------------------------------------------

def test_create_playlist(client):
    resp = client.post("/api/playlists", json={"name": "Road Trip", "description": "Highway songs"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Road Trip"
    assert body["description"] == "Highway songs"
    assert body["track_count"] == 0
    assert body["created_at"] is not None


def test_create_playlist_requires_name(client):
    resp = client.post("/api/playlists", json={"name": ""})
    assert resp.status_code == 422


def test_list_playlists(client):
    client.post("/api/playlists", json={"name": "A"})
    client.post("/api/playlists", json={"name": "B"})
    resp = client.get("/api/playlists")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert {"A", "B"} <= names


def test_get_playlist_returns_tracks(client):
    playlist_id = client.post("/api/playlists", json={"name": "Detail Test"}).json()["id"]
    song_id = make_song(title="Detail Song", file_path="/music/detail.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    resp = client.get(f"/api/playlists/{playlist_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["track_count"] == 1
    assert len(body["tracks"]) == 1
    assert body["tracks"][0]["song"]["title"] == "Detail Song"


def test_get_playlist_invalid_id_returns_404(client):
    resp = client.get("/api/playlists/999999")
    assert resp.status_code == 404


def test_rename_playlist(client):
    playlist_id = client.post("/api/playlists", json={"name": "Old Name"}).json()["id"]
    resp = client.put(f"/api/playlists/{playlist_id}", json={"name": "New Name"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"

    # description omitted -> unchanged
    resp2 = client.get(f"/api/playlists/{playlist_id}")
    assert resp2.json()["description"] == ""


def test_update_playlist_invalid_id_returns_404(client):
    resp = client.put("/api/playlists/999999", json={"name": "Nope"})
    assert resp.status_code == 404


def test_delete_playlist(client):
    playlist_id = client.post("/api/playlists", json={"name": "Delete Me"}).json()["id"]
    resp = client.delete(f"/api/playlists/{playlist_id}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/playlists/{playlist_id}")
    assert resp2.status_code == 404


def test_delete_playlist_invalid_id_returns_404(client):
    resp = client.delete("/api/playlists/999999")
    assert resp.status_code == 404


# ----------------------------------------------------------------------
# Track management
# ----------------------------------------------------------------------

def test_add_track_from_library(client):
    playlist_id = client.post("/api/playlists", json={"name": "Mix"}).json()["id"]
    song_id = make_song(title="Add Me", file_path="/music/add.mp3")

    resp = client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})
    assert resp.status_code == 201
    body = resp.json()
    assert body["song_id"] == song_id
    assert body["position"] == 0
    assert body["song"]["title"] == "Add Me"


def test_add_track_invalid_playlist_returns_404(client):
    song_id = make_song(file_path="/music/orphan.mp3")
    resp = client.post("/api/playlists/999999/tracks", json={"song_id": song_id})
    assert resp.status_code == 404


def test_add_track_missing_song_returns_404(client):
    playlist_id = client.post("/api/playlists", json={"name": "Mix"}).json()["id"]
    resp = client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": 999999})
    assert resp.status_code == 404


def test_add_track_preserves_order_across_requests(client):
    playlist_id = client.post("/api/playlists", json={"name": "Order Test"}).json()["id"]
    ids = [make_song(title=f"S{i}", file_path=f"/music/order{i}.mp3") for i in range(3)]
    for sid in ids:
        client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": sid})

    resp = client.get(f"/api/playlists/{playlist_id}")
    tracks = resp.json()["tracks"]
    assert [t["song_id"] for t in tracks] == ids
    assert [t["position"] for t in tracks] == [0, 1, 2]


def test_remove_track(client):
    playlist_id = client.post("/api/playlists", json={"name": "Remove Test"}).json()["id"]
    ids = [make_song(title=f"R{i}", file_path=f"/music/rem{i}.mp3") for i in range(2)]
    track_ids = [
        client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": sid}).json()["id"]
        for sid in ids
    ]

    resp = client.delete(f"/api/playlists/{playlist_id}/tracks/{track_ids[0]}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/playlists/{playlist_id}")
    tracks = resp2.json()["tracks"]
    assert len(tracks) == 1
    assert tracks[0]["song_id"] == ids[1]
    assert tracks[0]["position"] == 0  # gap closed


def test_remove_track_invalid_playlist_returns_404(client):
    resp = client.delete("/api/playlists/999999/tracks/1")
    assert resp.status_code == 404


def test_remove_track_invalid_track_id_returns_404(client):
    playlist_id = client.post("/api/playlists", json={"name": "Mix"}).json()["id"]
    resp = client.delete(f"/api/playlists/{playlist_id}/tracks/999999")
    assert resp.status_code == 404


def test_remove_track_belonging_to_different_playlist_returns_404(client):
    p1 = client.post("/api/playlists", json={"name": "P1"}).json()["id"]
    p2 = client.post("/api/playlists", json={"name": "P2"}).json()["id"]
    song_id = make_song(file_path="/music/cross.mp3")
    track_id = client.post(f"/api/playlists/{p1}/tracks", json={"song_id": song_id}).json()["id"]

    resp = client.delete(f"/api/playlists/{p2}/tracks/{track_id}")
    assert resp.status_code == 404
    # track is untouched under its real playlist
    assert len(client.get(f"/api/playlists/{p1}").json()["tracks"]) == 1


def test_reorder_tracks(client):
    playlist_id = client.post("/api/playlists", json={"name": "Reorder Test"}).json()["id"]
    ids = [make_song(title=f"O{i}", file_path=f"/music/reord{i}.mp3") for i in range(3)]
    track_ids = [
        client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": sid}).json()["id"]
        for sid in ids
    ]

    new_order = [track_ids[2], track_ids[0], track_ids[1]]
    resp = client.put(f"/api/playlists/{playlist_id}/tracks/reorder", json={"track_ids": new_order})
    assert resp.status_code == 200
    body = resp.json()
    assert [t["id"] for t in body] == new_order
    assert [t["position"] for t in body] == [0, 1, 2]


def test_reorder_tracks_invalid_playlist_returns_404(client):
    resp = client.put("/api/playlists/999999/tracks/reorder", json={"track_ids": [1, 2]})
    assert resp.status_code == 404


def test_reorder_tracks_bad_permutation_returns_400(client):
    playlist_id = client.post("/api/playlists", json={"name": "Bad Reorder"}).json()["id"]
    song_id = make_song(file_path="/music/badreorder.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    resp = client.put(f"/api/playlists/{playlist_id}/tracks/reorder", json={"track_ids": [999999]})
    assert resp.status_code == 400


def test_clear_tracks(client):
    playlist_id = client.post("/api/playlists", json={"name": "Clear Test"}).json()["id"]
    for i in range(3):
        sid = make_song(title=f"C{i}", file_path=f"/music/clear{i}.mp3")
        client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": sid})

    resp = client.delete(f"/api/playlists/{playlist_id}/tracks")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/playlists/{playlist_id}")
    assert resp2.json()["tracks"] == []
    assert resp2.json()["track_count"] == 0


def test_clear_tracks_invalid_playlist_returns_404(client):
    resp = client.delete("/api/playlists/999999/tracks")
    assert resp.status_code == 404


def test_deleting_playlist_does_not_delete_songs_from_library(client):
    playlist_id = client.post("/api/playlists", json={"name": "Ephemeral"}).json()["id"]
    song_id = make_song(title="Survivor", file_path="/music/survivor.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    client.delete(f"/api/playlists/{playlist_id}")

    resp = client.get(f"/api/library/songs/{song_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Survivor"


def test_deleting_song_removes_it_from_playlists(client):
    playlist_id = client.post("/api/playlists", json={"name": "Has Deleted Song"}).json()["id"]
    song_id = make_song(title="Doomed", file_path="/music/doomed.mp3")
    client.post(f"/api/playlists/{playlist_id}/tracks", json={"song_id": song_id})

    resp = client.delete(f"/api/library/songs/{song_id}")
    assert resp.status_code == 204

    resp2 = client.get(f"/api/playlists/{playlist_id}")
    assert resp2.json()["tracks"] == []
