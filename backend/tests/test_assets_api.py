"""
tests/test_assets_api.py
==========================

HTTP-level tests for the Jingle & Advertisement Library API (V0.5
Part 1), via FastAPI's TestClient.
"""

from __future__ import annotations

import pytest

from app.database.models import Song


def _import(client, file_path, *, name="Test Asset", asset_type="JINGLE", category="", description=""):
    return client.post(
        "/api/assets",
        json={
            "file_path": str(file_path),
            "name": name,
            "asset_type": asset_type,
            "category": category,
            "description": description,
        },
    )


# ----------------------------------------------------------------------
# 1 & 2. Import jingle / advertisement
# ----------------------------------------------------------------------


def test_import_jingle(client, make_asset_wav):
    path = make_asset_wav("station_id.wav")
    resp = _import(client, path, name="Station ID", asset_type="JINGLE", category="ID")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Station ID"
    assert body["asset_type"] == "JINGLE"
    assert body["category"] == "ID"
    assert body["enabled"] is True
    assert body["id"] is not None


def test_import_advertisement(client, make_asset_wav):
    path = make_asset_wav("ad_spot.wav")
    resp = _import(client, path, name="Pizza Ad", asset_type="ADVERTISEMENT", category="Food")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Pizza Ad"
    assert body["asset_type"] == "ADVERTISEMENT"


# ----------------------------------------------------------------------
# 3. List assets
# ----------------------------------------------------------------------


def test_list_assets(client, make_asset_wav):
    _import(client, make_asset_wav("a.wav"), name="A", asset_type="JINGLE")
    _import(client, make_asset_wav("b.wav"), name="B", asset_type="ADVERTISEMENT")

    resp = client.get("/api/assets")
    assert resp.status_code == 200
    names = {a["name"] for a in resp.json()}
    assert names == {"A", "B"}


# ----------------------------------------------------------------------
# 4. Get asset
# ----------------------------------------------------------------------


def test_get_asset(client, make_asset_wav):
    created = _import(client, make_asset_wav("get.wav"), name="Get Me").json()
    resp = client.get(f"/api/assets/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Me"


# ----------------------------------------------------------------------
# 5. Update asset
# ----------------------------------------------------------------------


def test_update_asset(client, make_asset_wav):
    created = _import(client, make_asset_wav("update.wav"), name="Old Name", category="Old").json()
    resp = client.put(
        f"/api/assets/{created['id']}",
        json={"name": "New Name", "category": "New", "description": "Updated"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["category"] == "New"
    assert body["description"] == "Updated"
    # file_path/asset_type/duration are immutable via update.
    assert body["asset_type"] == "JINGLE"


# ----------------------------------------------------------------------
# 6. Delete asset
# ----------------------------------------------------------------------


def test_delete_asset(client, make_asset_wav):
    created = _import(client, make_asset_wav("delete.wav"), name="Delete Me").json()
    resp = client.delete(f"/api/assets/{created['id']}")
    assert resp.status_code == 204

    follow_up = client.get(f"/api/assets/{created['id']}")
    assert follow_up.status_code == 404


# ----------------------------------------------------------------------
# 7 & 8. Enable / disable asset
# ----------------------------------------------------------------------


def test_disable_and_enable_asset(client, make_asset_wav):
    created = _import(client, make_asset_wav("toggle.wav"), name="Toggle Me").json()

    disable_resp = client.post(f"/api/assets/{created['id']}/disable")
    assert disable_resp.status_code == 200
    assert disable_resp.json()["enabled"] is False

    enable_resp = client.post(f"/api/assets/{created['id']}/enable")
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True


# ----------------------------------------------------------------------
# 9. Search assets
# ----------------------------------------------------------------------


def test_search_assets(client, make_asset_wav):
    _import(client, make_asset_wav("s1.wav"), name="Morning Jingle", category="Morning")
    _import(client, make_asset_wav("s2.wav"), name="Evening Jingle", category="Evening")

    resp = client.get("/api/assets", params={"search": "Morning"})
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert names == ["Morning Jingle"]


# ----------------------------------------------------------------------
# 10 & 11. Filter by asset type
# ----------------------------------------------------------------------


def test_filter_jingle(client, make_asset_wav):
    _import(client, make_asset_wav("j.wav"), name="J", asset_type="JINGLE")
    _import(client, make_asset_wav("ad.wav"), name="Ad", asset_type="ADVERTISEMENT")

    resp = client.get("/api/assets", params={"asset_type": "JINGLE"})
    assert resp.status_code == 200
    types = {a["asset_type"] for a in resp.json()}
    assert types == {"JINGLE"}


def test_filter_advertisement(client, make_asset_wav):
    _import(client, make_asset_wav("j2.wav"), name="J2", asset_type="JINGLE")
    _import(client, make_asset_wav("ad2.wav"), name="Ad2", asset_type="ADVERTISEMENT")

    resp = client.get("/api/assets", params={"asset_type": "ADVERTISEMENT"})
    assert resp.status_code == 200
    types = {a["asset_type"] for a in resp.json()}
    assert types == {"ADVERTISEMENT"}


# ----------------------------------------------------------------------
# 12. Filter by category
# ----------------------------------------------------------------------


def test_filter_category(client, make_asset_wav):
    _import(client, make_asset_wav("c1.wav"), name="C1", category="Sports")
    _import(client, make_asset_wav("c2.wav"), name="C2", category="Weather")

    resp = client.get("/api/assets", params={"category": "Sports"})
    assert resp.status_code == 200
    categories = {a["category"] for a in resp.json()}
    assert categories == {"Sports"}


# ----------------------------------------------------------------------
# 13. Missing file rejected
# ----------------------------------------------------------------------


def test_missing_file_rejected(client, tmp_path):
    resp = _import(client, tmp_path / "does_not_exist.wav")
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# 14. Unsupported format rejected
# ----------------------------------------------------------------------


def test_unsupported_format_rejected(client, tmp_path):
    bad_path = tmp_path / "notes.txt"
    bad_path.write_text("not audio")
    resp = _import(client, bad_path)
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# 15. Corrupt audio rejected
# ----------------------------------------------------------------------


def test_corrupt_audio_rejected(client, tmp_path):
    corrupt_path = tmp_path / "corrupt.mp3"
    corrupt_path.write_bytes(b"this is not really an mp3, just garbage bytes")
    resp = _import(client, corrupt_path)
    assert resp.status_code == 400


# ----------------------------------------------------------------------
# 16. Duration detected correctly
# ----------------------------------------------------------------------


def test_duration_detected_correctly(client, make_asset_wav):
    path = make_asset_wav("timed.wav", duration_seconds=1.5)
    resp = _import(client, path, name="Timed")
    assert resp.status_code == 201
    assert resp.json()["duration"] == pytest.approx(1.5, abs=0.05)


# ----------------------------------------------------------------------
# 17. Invalid asset type rejected
# ----------------------------------------------------------------------


def test_invalid_asset_type_rejected(client, make_asset_wav):
    path = make_asset_wav("invalid_type.wav")
    resp = client.post(
        "/api/assets",
        json={
            "file_path": str(path),
            "name": "Bad Type",
            "asset_type": "MUSIC",
        },
    )
    assert resp.status_code == 422  # Pydantic pattern validation


# ----------------------------------------------------------------------
# 18. Missing asset returns 404
# ----------------------------------------------------------------------


def test_missing_asset_returns_404(client):
    assert client.get("/api/assets/999999").status_code == 404
    assert client.put("/api/assets/999999", json={"name": "X"}).status_code == 404
    assert client.delete("/api/assets/999999").status_code == 404
    assert client.post("/api/assets/999999/enable").status_code == 404
    assert client.post("/api/assets/999999/disable").status_code == 404


# ----------------------------------------------------------------------
# 19. Disabled asset remains available (still retrievable, still listed)
# ----------------------------------------------------------------------


def test_disabled_asset_remains_available(client, make_asset_wav):
    created = _import(client, make_asset_wav("still_here.wav"), name="Still Here").json()
    client.post(f"/api/assets/{created['id']}/disable")

    get_resp = client.get(f"/api/assets/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["enabled"] is False

    list_resp = client.get("/api/assets")
    ids = [a["id"] for a in list_resp.json()]
    assert created["id"] in ids


# ----------------------------------------------------------------------
# 20. Existing Music Library records remain unaffected
# ----------------------------------------------------------------------


def test_deleting_asset_does_not_affect_music_library(client, db_session, make_song, make_asset_wav):
    song = make_song(title="Untouched Song")
    created = _import(client, make_asset_wav("delete_isolated.wav"), name="Isolated Asset").json()

    resp = client.delete(f"/api/assets/{created['id']}")
    assert resp.status_code == 204

    still_there = db_session.get(Song, song.id)
    assert still_there is not None
    assert still_there.title == "Untouched Song"
