"""
tests/test_queue_engine_integration.py
=========================================

Integration tests for the final V0.3 piece: Queue <-> V0.1 AudioEngine.

Uses the real `AudioEngine`/`Player` state machine throughout - only
the decoder and audio-output hardware seams are faked (see
`tests/fakes.py`), so what's under test is the real callback wiring
(`QueueManager` <-> `engine.on_track_end`) and the real `QueueRepository`
/ `SongRepository` behavior, driven through the real FastAPI routes.
"""

from __future__ import annotations

from app.database.models import QueueItemStatus


def _queue_from_db(db_session):
    from app.database.repositories.queue_repository import QueueRepository

    return list(QueueRepository(db_session).list_all())


# ---------------------------------------------------------------------
# 1. Playlist -> Queue
# ---------------------------------------------------------------------

def test_playlist_tracks_are_appended_to_queue_in_order(client, db_session, make_song):
    from app.database.repositories.playlist_repository import PlaylistRepository

    song_a = make_song(title="A")
    song_b = make_song(title="B")
    song_c = make_song(title="C")

    playlist_repo = PlaylistRepository(db_session)
    playlist = playlist_repo.create("My Playlist")
    playlist_repo.add_track(playlist.id, song_a.id)
    playlist_repo.add_track(playlist.id, song_b.id)
    playlist_repo.add_track(playlist.id, song_c.id)
    db_session.commit()

    response = client.post(f"/api/queue/playlist/{playlist.id}")
    assert response.status_code == 201
    body = response.json()
    assert [item["song_id"] for item in body] == [song_a.id, song_b.id, song_c.id]
    assert [item["position"] for item in body] == [0, 1, 2]
    assert all(item["status"] == QueueItemStatus.QUEUED.value for item in body)

    queue_response = client.get("/api/queue")
    assert [item["song_id"] for item in queue_response.json()] == [song_a.id, song_b.id, song_c.id]


# ---------------------------------------------------------------------
# 2. Queue -> Audio Engine
# ---------------------------------------------------------------------

def test_playing_the_queue_loads_and_plays_first_track_on_the_engine(client, fake_engine, make_song):
    song = make_song(title="First")
    fake_engine._test_decoder.register(song.file_path)

    add = client.post("/api/queue", json={"song_id": song.id})
    assert add.status_code == 201
    queue_item_id = add.json()["id"]

    response = client.post("/api/queue/play")
    assert response.status_code == 200
    assert response.json()["state"] == "PLAYING"
    assert response.json()["file_path"] == song.file_path
    assert fake_engine.is_playing()

    queue_after = client.get("/api/queue").json()
    assert queue_after[0]["id"] == queue_item_id
    assert queue_after[0]["status"] == QueueItemStatus.PLAYING.value


# ---------------------------------------------------------------------
# 3. Track completion -> Next track
# ---------------------------------------------------------------------

def test_natural_completion_advances_to_the_next_queued_track(client, fake_engine, make_song):
    song_a = make_song(title="A")
    song_b = make_song(title="B")
    fake_engine._test_decoder.register(song_a.file_path)
    fake_engine._test_decoder.register(song_b.file_path)

    client.post("/api/queue", json={"song_id": song_a.id})
    client.post("/api/queue", json={"song_id": song_b.id})
    play = client.post("/api/queue/play")
    assert play.json()["file_path"] == song_a.file_path

    # Simulate the A track reaching natural end-of-data.
    fake_engine._test_output.simulate_completion()

    status = client.get("/api/playback/status").json()
    assert status["state"] == "PLAYING"
    assert status["file_path"] == song_b.file_path

    queue = client.get("/api/queue").json()
    by_song = {item["song_id"]: item["status"] for item in queue}
    assert by_song[song_a.id] == QueueItemStatus.PLAYED.value
    assert by_song[song_b.id] == QueueItemStatus.PLAYING.value


def test_play_next_insertion_is_honored_by_auto_advance(client, fake_engine, make_song):
    """A song queued with play_next=True while something is already
    PLAYING should be the one auto-advance picks next - not whatever
    was appended to the tail earlier."""
    song_a = make_song(title="A")
    song_b_tail = make_song(title="B (appended earlier)")
    song_c_next = make_song(title="C (play next)")
    for s in (song_a, song_b_tail, song_c_next):
        fake_engine._test_decoder.register(s.file_path)

    client.post("/api/queue", json={"song_id": song_a.id})
    client.post("/api/queue", json={"song_id": song_b_tail.id})
    client.post("/api/queue/play")  # A starts playing

    client.post("/api/queue", json={"song_id": song_c_next.id, "play_next": True})

    fake_engine._test_output.simulate_completion()  # A finishes

    status = client.get("/api/playback/status").json()
    assert status["file_path"] == song_c_next.file_path


# ---------------------------------------------------------------------
# 4. Queue completion (empty queue -> stop cleanly)
# ---------------------------------------------------------------------

def test_queue_becoming_empty_stops_playback_cleanly(client, fake_engine, make_song):
    song = make_song(title="Only Track")
    fake_engine._test_decoder.register(song.file_path)

    client.post("/api/queue", json={"song_id": song.id})
    client.post("/api/queue/play")
    assert fake_engine.is_playing()

    fake_engine._test_output.simulate_completion()

    status = client.get("/api/playback/status").json()
    assert status["state"] in ("STOPPED", "IDLE")
    assert not fake_engine.is_playing()

    queue = client.get("/api/queue").json()
    assert queue[0]["status"] == QueueItemStatus.PLAYED.value
    assert not any(item["status"] == QueueItemStatus.PLAYING.value for item in queue)
    assert not any(item["status"] == QueueItemStatus.QUEUED.value for item in queue)


# ---------------------------------------------------------------------
# 5. Playback failure (missing file, and corrupt/undecodable file)
# ---------------------------------------------------------------------

def test_missing_file_is_marked_failed_and_skipped(client, fake_engine, make_song):
    missing_song = make_song(title="Missing", missing=True)
    good_song = make_song(title="Good")
    fake_engine._test_decoder.register(good_song.file_path)

    client.post("/api/queue", json={"song_id": missing_song.id})
    client.post("/api/queue", json={"song_id": good_song.id})

    response = client.post("/api/queue/play")
    assert response.status_code == 200
    assert response.json()["file_path"] == good_song.file_path

    queue = client.get("/api/queue").json()
    by_song = {item["song_id"]: item["status"] for item in queue}
    assert by_song[missing_song.id] == QueueItemStatus.FAILED.value
    assert by_song[good_song.id] == QueueItemStatus.PLAYING.value


def test_undecodable_file_is_marked_failed_and_skipped(client, fake_engine, make_song):
    """File exists on disk (passes the existence/extension check) but
    was never registered with the fake decoder, simulating a
    corrupt/unreadable file that fails to decode."""
    corrupt_song = make_song(title="Corrupt")
    good_song = make_song(title="Good")
    fake_engine._test_decoder.register(good_song.file_path)
    # corrupt_song.file_path deliberately NOT registered.

    client.post("/api/queue", json={"song_id": corrupt_song.id})
    client.post("/api/queue", json={"song_id": good_song.id})

    response = client.post("/api/queue/play")
    assert response.status_code == 200
    assert response.json()["file_path"] == good_song.file_path

    queue = client.get("/api/queue").json()
    by_song = {item["song_id"]: item["status"] for item in queue}
    assert by_song[corrupt_song.id] == QueueItemStatus.FAILED.value


def test_all_tracks_failing_leaves_queue_empty_and_returns_409(client, fake_engine, make_song):
    missing_song = make_song(title="Missing", missing=True)
    client.post("/api/queue", json={"song_id": missing_song.id})

    response = client.post("/api/queue/play")
    assert response.status_code == 409

    queue = client.get("/api/queue").json()
    assert queue[0]["status"] == QueueItemStatus.FAILED.value
    assert not fake_engine.is_playing()


# ---------------------------------------------------------------------
# 6. Manual Stop (must NOT auto-advance)
# ---------------------------------------------------------------------

def test_manual_stop_does_not_auto_advance(client, fake_engine, make_song):
    song_a = make_song(title="A")
    song_b = make_song(title="B")
    fake_engine._test_decoder.register(song_a.file_path)
    fake_engine._test_decoder.register(song_b.file_path)

    client.post("/api/queue", json={"song_id": song_a.id})
    client.post("/api/queue", json={"song_id": song_b.id})
    client.post("/api/queue/play")
    assert fake_engine.is_playing()

    stop_response = client.post("/api/playback/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["state"] == "STOPPED"

    # Crucially: no auto-advance. B must still be QUEUED, not PLAYING.
    assert not fake_engine.is_playing()
    queue = client.get("/api/queue").json()
    by_song = {item["song_id"]: item["status"] for item in queue}
    assert by_song[song_a.id] == QueueItemStatus.SKIPPED.value
    assert by_song[song_b.id] == QueueItemStatus.QUEUED.value

    status = client.get("/api/playback/status").json()
    assert status["state"] == "STOPPED"
