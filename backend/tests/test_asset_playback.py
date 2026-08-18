from __future__ import annotations

import time

from app.database.models import (
    Asset,
    AssetPlaybackState,
)

from app.services import asset_service


def _make_asset(
    db_session,
    make_asset_mp3,
    fake_engine,
    *,
    name="Test Jingle",
    asset_type="JINGLE",
    cooldown_seconds=0,
    enabled=True,
):
    path = make_asset_mp3(
        f"{name.replace(' ', '_')}.mp3"
    )

    asset = asset_service.import_asset(
        db_session,
        file_path=str(path),
        name=name,
        asset_type=asset_type,
        cooldown_seconds=cooldown_seconds,
    )

    if not enabled:
        asset_service.disable_asset(
            db_session,
            asset.id,
        )

    # Register the same path with the fake decoder so
    # the real AudioEngine can load it during the test.
    fake_engine._test_decoder.register(
        str(path),
        duration_seconds=0.05,
    )

    return asset


def test_play_valid_jingle(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
    )

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["asset_id"] == asset.id
    assert body["asset_type"] == "JINGLE"
    assert body["state"] == "PLAYING"
    assert body["play_count"] == 1


def test_play_valid_advertisement(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="Car Advertisement",
        asset_type="ADVERTISEMENT",
    )

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 200
    assert response.json()["asset_type"] == "ADVERTISEMENT"


def test_missing_asset_returns_404(client):
    response = client.post(
        "/api/assets/999999/play"
    )

    assert response.status_code == 404


def test_disabled_asset_returns_409(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="Disabled Jingle",
        enabled=False,
    )

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 409


def test_missing_audio_file_returns_409(
    client,
    db_session,
):
    asset = Asset(
        name="Missing File",
        asset_type="JINGLE",
        file_path="D:\\does-not-exist\\missing.mp3",
        duration=1.0,
        category="",
        description="",
        enabled=True,
        priority=0,
        cooldown_seconds=0,
    )

    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 409


def test_undecodable_audio_returns_422(
    client,
    db_session,
    tmp_path,
):
    path = tmp_path / "corrupt.mp3"
    path.write_bytes(b"not-a-real-mp3")

    asset = Asset(
        name="Corrupt Audio",
        asset_type="JINGLE",
        file_path=str(path),
        duration=1.0,
        category="",
        description="",
        enabled=True,
        priority=0,
        cooldown_seconds=0,
    )

    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 422


def test_cooldown_blocks_repeat(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="Cooldown Advertisement",
        asset_type="ADVERTISEMENT",
        cooldown_seconds=60,
    )

    first = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert first.status_code == 200

    second = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert second.status_code == 409
    assert "cooldown" in (
        second.json()["detail"].lower()
    )


def test_zero_cooldown_allows_repeat(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="No Cooldown Jingle",
        cooldown_seconds=0,
    )

    first = client.post(
        f"/api/assets/{asset.id}/play"
    )

    second = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert first.status_code == 200
    assert second.status_code == 200


def test_completion_updates_state(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="Completion Jingle",
    )

    response = client.post(
        f"/api/assets/{asset.id}/play"
    )

    assert response.status_code == 200

    fake_engine._test_output.simulate_completion()

    row = (
        db_session.query(
            AssetPlaybackState
        )
        .filter_by(asset_id=asset.id)
        .one()
    )

    assert row.state == "COMPLETED"
    assert row.started_at is not None
    assert row.last_played_at is not None
    assert row.completed_at is not None
    assert row.play_count == 1


def test_playback_status_endpoint(
    client,
    db_session,
    fake_engine,
    make_asset_mp3,
):
    asset = _make_asset(
        db_session,
        make_asset_mp3,
        fake_engine,
        name="Status Jingle",
    )

    client.post(
        f"/api/assets/{asset.id}/play"
    )

    response = client.get(
        f"/api/assets/{asset.id}/playback-status"
    )

    assert response.status_code == 200
    assert response.json()["state"] == "PLAYING"


def test_existing_song_playback_still_works(
    client,
    music_folder,
    fake_engine,
):
    response = client.post(
        "/api/library/scan",
        json={
            "folder_path": str(music_folder)
        },
    )

    assert response.status_code == 202

    job_id = response.json()["job_id"]

    for _ in range(200):
        status = client.get(
            f"/api/library/scan/{job_id}"
        ).json()

        if status["status"] == "completed":
            break

        time.sleep(0.05)

    assert status["status"] == "completed"

    songs = client.get(
        "/api/library/songs"
    ).json()

    assert songs

    song = songs[0]

    # The library scan creates real audio files, but the test engine
    # intentionally uses FakeDecoder. Register the scanned file with
    # that fake decoder before calling the existing playback API.
    fake_engine._test_decoder.register(
        song["file_path"],
        duration_seconds=max(
            0.05,
            float(song.get("duration") or 0.05),
        ),
    )

    response = client.post(
        "/api/playback/play-song",
        json={
            "song_id": song["id"]
        },
    )

    assert response.status_code == 200