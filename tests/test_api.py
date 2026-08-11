"""tests/test_api.py — FastAPI endpoint tests for the Music Library API."""

from __future__ import annotations

import time


def _scan_and_wait(client, folder_path: str, timeout: float = 10.0) -> dict:
    resp = client.post("/api/library/scan", json={"folder_path": folder_path})
    assert resp.status_code == 202
    job = resp.json()

    deadline = time.time() + timeout
    while time.time() < deadline:
        status_resp = client.get(f"/api/library/scan/{job['job_id']}")
        assert status_resp.status_code == 200
        job = status_resp.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
    raise TimeoutError("scan job did not complete in time")


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_scan_endpoint_returns_job_and_completes(client, music_folder):
    job = _scan_and_wait(client, str(music_folder))
    assert job["status"] == "completed"
    assert job["added"] == 3
    assert job["errors"] == 0


def test_scan_endpoint_rejects_invalid_folder(client, tmp_path):
    resp = client.post("/api/library/scan", json={"folder_path": str(tmp_path / "missing")})
    assert resp.status_code == 400


def test_scan_status_unknown_job_404(client):
    resp = client.get("/api/library/scan/not-a-real-job")
    assert resp.status_code == 404


def test_list_songs_after_scan(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    resp = client.get("/api/library/songs")
    assert resp.status_code == 200
    songs = resp.json()
    assert len(songs) == 3
    titles = {s["title"] for s in songs}
    assert titles == {"Tum Hi Ho", "Kesariya", "Song 3"}


def test_get_song_by_id(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    song_id = client.get("/api/library/songs").json()[0]["id"]

    resp = client.get(f"/api/library/songs/{song_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == song_id

    missing = client.get("/api/library/songs/999999")
    assert missing.status_code == 404


def test_search_endpoint(client, music_folder):
    _scan_and_wait(client, str(music_folder))

    by_title = client.get("/api/library/search", params={"q": "Kesariya"}).json()
    assert len(by_title) == 1
    assert by_title[0]["title"] == "Kesariya"

    by_artist = client.get("/api/library/search", params={"q": "Arijit"}).json()
    assert len(by_artist) == 2

    no_match = client.get("/api/library/search", params={"q": "Nonexistent Song XYZ"}).json()
    assert no_match == []


def test_filter_endpoint(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    resp = client.get("/api/library/filter", params={"genre": "Bollywood"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_stats_endpoint(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    resp = client.get("/api/library/stats")
    assert resp.status_code == 200
    stats = resp.json()

    assert stats["total_songs"] == 3
    assert stats["available"] == 3
    assert stats["unavailable"] == 0
    # Both mp3s are tagged "Arijit Singh"; the untagged wav falls back
    # to "Unknown Artist" -> 2 distinct artists.
    assert stats["artists"] == 2
    assert stats["total_duration_seconds"] > 0


def test_delete_song(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    song_id = client.get("/api/library/songs").json()[0]["id"]

    resp = client.delete(f"/api/library/songs/{song_id}")
    assert resp.status_code == 204

    assert client.get(f"/api/library/songs/{song_id}").status_code == 404
    assert client.delete(f"/api/library/songs/{song_id}").status_code == 404


def test_refresh_endpoint_marks_missing_file_unavailable(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    songs = client.get("/api/library/songs").json()
    target = next(s for s in songs if s["file_name"] == "Kesariya.mp3")

    import os
    os.remove(target["file_path"])

    resp = client.post("/api/library/refresh")
    assert resp.status_code == 200
    assert resp.json()["disabled"] == 1

    refreshed = client.get(f"/api/library/songs/{target['id']}").json()
    assert refreshed["enabled"] is False


def test_rescan_endpoint(client, music_folder):
    _scan_and_wait(client, str(music_folder))

    from tests.conftest import _make_silent_wav
    _make_silent_wav(music_folder / "Another New Track.wav")

    resp = client.post("/api/library/rescan")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) == 1
    assert jobs[0]["added"] == 1

    assert len(client.get("/api/library/songs").json()) == 4


def test_stats_reflect_unavailable_after_disable(client, music_folder):
    _scan_and_wait(client, str(music_folder))
    songs = client.get("/api/library/songs").json()
    import os
    os.remove(songs[0]["file_path"])
    client.post("/api/library/refresh")

    stats = client.get("/api/library/stats").json()
    assert stats["available"] == 2
    assert stats["unavailable"] == 1
    assert stats["total_songs"] == 3  # soft-disabled, not deleted
