"""
V0.8 Part 2 — Live Assist API tests.
"""

from __future__ import annotations


def test_live_assist_status_returns_real_engine_state(client, fake_engine):
    response = client.get("/api/live-assist/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] in {"IDLE", "STOPPED", "PAUSED", "PLAYING", "ERROR"}
    assert body["volume"] == 1.0


def test_live_assist_volume_updates_shared_engine(client, fake_engine):
    response = client.post("/api/live-assist/volume", json={"volume": 0.35})

    assert response.status_code == 200
    assert response.json()["volume"] == 0.35
    assert fake_engine.get_volume() == 0.35


def test_live_assist_volume_rejects_out_of_range(client, fake_engine):
    response = client.post("/api/live-assist/volume", json={"volume": 1.5})

    assert response.status_code == 422
    assert fake_engine.get_volume() == 1.0


def test_live_assist_volume_rejects_negative(client, fake_engine):
    response = client.post("/api/live-assist/volume", json={"volume": -0.1})

    assert response.status_code == 422
    assert fake_engine.get_volume() == 1.0
