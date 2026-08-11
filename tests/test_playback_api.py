"""
tests/test_playback_api.py
============================

Verifies the V0.2 playback endpoints correctly delegate to the
*existing, unmodified* V0.1 `AudioEngine` rather than reimplementing
playback. A fake `AudioOutputBase` is injected (same extension point
V0.1's own test suite would use) so these tests don't need real sound
hardware and don't touch/duplicate V0.1's playback logic.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np
import pytest

from app.api import engine_provider
from src import AudioEngine
from src.audio_output import AudioOutputBase


class FakeAudioOutput(AudioOutputBase):
    """Minimal in-memory stand-in for the real sound-card backend."""

    def __init__(self) -> None:
        self._active = False
        self._read_callback: Optional[Callable[[int], np.ndarray]] = None

    def open(self, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    def start(self, read_callback, on_finished) -> None:
        self._read_callback = read_callback
        self._on_finished = on_finished
        self._active = True

    def pause(self) -> None:
        self._active = False

    def resume(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    def close(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


@pytest.fixture()
def fake_engine():
    engine = AudioEngine(audio_output=FakeAudioOutput())
    engine_provider.set_engine(engine)
    yield engine
    engine_provider.shutdown_engine()


def test_play_song_by_id_uses_v01_engine(client, music_folder, fake_engine):
    scan = client.post("/api/library/scan", json={"folder_path": str(music_folder)})
    job_id = scan.json()["job_id"]
    import time
    for _ in range(200):
        status = client.get(f"/api/library/scan/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(0.05)

    song = client.get("/api/library/songs").json()[0]

    resp = client.post("/api/playback/play-song", json={"song_id": song["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_path"] == song["file_path"]
    assert body["state"].lower() == "playing"

    # Play count on the library record was incremented via the same
    # SongRepository used by the rest of the API - no parallel tracking.
    refreshed = client.get(f"/api/library/songs/{song['id']}").json()
    assert refreshed["play_count"] == 1
    assert refreshed["last_played"] is not None


def test_play_missing_song_returns_404(client, fake_engine):
    resp = client.post("/api/playback/play-song", json={"song_id": 999999})
    assert resp.status_code == 404


def test_play_disabled_song_returns_409(client, music_folder, fake_engine, db_session):
    from app.database.repositories.song_repository import SongRepository
    from app.services import library_service

    library_service.scan_folder_sync(db_session, str(music_folder))
    song = SongRepository(db_session).list_all()[0]
    SongRepository(db_session).set_enabled(song.id, False)
    db_session.commit()

    resp = client.post("/api/playback/play-song", json={"song_id": song.id})
    assert resp.status_code == 409


def test_pause_resume_stop_status_roundtrip(client, music_folder, fake_engine):
    scan = client.post("/api/library/scan", json={"folder_path": str(music_folder)})
    job_id = scan.json()["job_id"]
    import time
    for _ in range(200):
        status = client.get(f"/api/library/scan/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(0.05)

    song = client.get("/api/library/songs").json()[0]
    client.post("/api/playback/play-song", json={"song_id": song["id"]})

    assert client.post("/api/playback/pause").json()["state"].lower() == "paused"
    assert client.post("/api/playback/resume").json()["state"].lower() == "playing"
    assert client.post("/api/playback/stop").json()["state"].lower() == "stopped"
    assert client.get("/api/playback/status").status_code == 200
