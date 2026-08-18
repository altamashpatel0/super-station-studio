from __future__ import annotations

from app.database.models import Asset, AssetType, Playlist, Song


def _song(db):
    song = Song(
        file_path="/tmp/v06-scheduler-song.mp3",
        file_name="v06-scheduler-song.mp3",
        title="Scheduler Song",
        artist="Test Artist",
        album="Test Album",
        album_artist="Test Artist",
        genre="Test",
        duration=10.0,
        file_size=1,
        format="MP3",
        enabled=True,
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


def _playlist(db):
    row = Playlist(name="Scheduler Playlist", description="test")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _asset(db, asset_type):
    row = Asset(
        name=f"Scheduler {asset_type.value}",
        asset_type=asset_type,
        file_path=f"/tmp/v06-{asset_type.value.lower()}.mp3",
        duration=5.0,
        category="test",
        description="test",
        enabled=True,
        priority=1,
        cooldown_seconds=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _payload(target_type, target_id, **overrides):
    data = {
        "name": "Morning Schedule",
        "target_type": target_type,
        "target_id": target_id,
        "start_time": "09:00",
        "end_time": "10:00",
        "days_of_week": [0, 2, 4],
        "enabled": True,
    }
    data.update(overrides)
    return data


def test_create_valid_schedule(client, db_session):
    song = _song(db_session)
    r = client.post("/api/schedules", json=_payload("SONG", song.id))
    assert r.status_code == 201
    body = r.json()
    assert body["target_type"] == "SONG"
    assert body["target_id"] == song.id
    assert body["days_of_week"] == [0, 2, 4]


def test_invalid_input_is_rejected(client, db_session):
    song = _song(db_session)
    assert client.post("/api/schedules", json=_payload("SONG", song.id, name="")).status_code == 422
    assert client.post("/api/schedules", json=_payload("INVALID", song.id)).status_code == 422
    assert client.post("/api/schedules", json=_payload("SONG", song.id, days_of_week=[7])).status_code == 422
    assert client.post("/api/schedules", json=_payload("SONG", song.id, start_time="25:00")).status_code == 422
    assert client.post("/api/schedules", json=_payload("SONG", song.id, start_time="10:00", end_time="09:00")).status_code == 422


def test_target_must_exist(client):
    r = client.post("/api/schedules", json=_payload("SONG", 999999))
    assert r.status_code == 400


def test_asset_target_types_and_matching(client, db_session):
    jingle = _asset(db_session, AssetType.JINGLE)
    ad = _asset(db_session, AssetType.ADVERTISEMENT)

    assert client.post("/api/schedules", json=_payload("JINGLE", jingle.id)).status_code == 201
    assert client.post("/api/schedules", json=_payload("ADVERTISEMENT", ad.id)).status_code == 201

    wrong = client.post("/api/schedules", json=_payload("ADVERTISEMENT", jingle.id))
    assert wrong.status_code == 400


def test_playlist_target(client, db_session):
    playlist = _playlist(db_session)
    assert client.post("/api/schedules", json=_payload("PLAYLIST", playlist.id)).status_code == 201


def test_get_and_list_with_day_filter(client, db_session):
    song = _song(db_session)
    created = client.post(
        "/api/schedules",
        json=_payload("SONG", song.id, days_of_week=[0, 2]),
    ).json()

    assert client.get(f"/api/schedules/{created['id']}").status_code == 200
    assert len(client.get("/api/schedules", params={"day": 0}).json()) == 1
    assert client.get("/api/schedules", params={"day": 1}).json() == []


def test_update_schedule(client, db_session):
    song = _song(db_session)
    created = client.post("/api/schedules", json=_payload("SONG", song.id)).json()

    r = client.put(
        f"/api/schedules/{created['id']}",
        json={
            "name": "Updated Schedule",
            "start_time": "11:00",
            "end_time": "12:30",
            "days_of_week": [1, 3, 5],
        },
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Schedule"
    assert r.json()["days_of_week"] == [1, 3, 5]


def test_enable_disable_and_enabled_filter(client, db_session):
    song = _song(db_session)
    created = client.post("/api/schedules", json=_payload("SONG", song.id)).json()

    r = client.post(f"/api/schedules/{created['id']}/disable")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert client.get("/api/schedules", params={"enabled_only": True}).json() == []

    r = client.post(f"/api/schedules/{created['id']}/enable")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_delete_and_missing_schedule_errors(client, db_session):
    song = _song(db_session)
    created = client.post("/api/schedules", json=_payload("SONG", song.id)).json()

    assert client.delete(f"/api/schedules/{created['id']}").status_code == 204
    assert client.get(f"/api/schedules/{created['id']}").status_code == 404
    assert client.delete("api/schedules/999999").status_code in (404, 307)
    assert client.get("/api/schedules/999999").status_code == 404
