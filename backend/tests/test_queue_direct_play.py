from app.database.models import QueueItemStatus


def test_direct_play_of_second_queued_item_preempts_current(client, fake_engine, make_song):
    song_a = make_song(title="A")
    song_b = make_song(title="B")
    song_c = make_song(title="C")
    for song in (song_a, song_b, song_c):
        fake_engine._test_decoder.register(song.file_path)

    a = client.post("/api/queue", json={"song_id": song_a.id}).json()
    b = client.post("/api/queue", json={"song_id": song_b.id}).json()
    c = client.post("/api/queue", json={"song_id": song_c.id}).json()

    first = client.post("/api/queue/play")
    assert first.status_code == 200
    assert first.json()["file_path"] == song_a.file_path

    # Operator clicks the second queue row while A is playing.
    second = client.post(f"/api/queue/play?queue_item_id={b['id']}")
    assert second.status_code == 200
    assert second.json()["file_path"] == song_b.file_path

    queue = client.get("/api/queue").json()
    by_id = {item["id"]: item for item in queue}

    assert by_id[a["id"]]["status"] == QueueItemStatus.SKIPPED.value
    assert by_id[b["id"]]["status"] == QueueItemStatus.PLAYING.value
    assert by_id[c["id"]]["status"] == QueueItemStatus.QUEUED.value


def test_clear_queue_repository_is_empty_after_clear(db_session, make_song):
    from app.database.repositories.queue_repository import QueueRepository

    song = make_song(title="Clear Me")
    repo = QueueRepository(db_session)
    repo.add_track(song.id)
    repo.add_track(song.id)
    assert len(list(repo.list_all())) == 2

    removed = repo.clear()
    db_session.commit()

    assert removed == 2
    assert list(repo.list_all()) == []
