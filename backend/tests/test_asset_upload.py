from pathlib import Path


def test_browser_asset_upload_imports_real_audio(client, make_asset_wav):
    path = make_asset_wav("browser-upload.wav", duration_seconds=0.5)
    with path.open("rb") as fh:
        response = client.post(
            "/api/assets/upload",
            files={"file": (path.name, fh, "audio/wav")},
            data={
                "name": "Browser Jingle",
                "asset_type": "JINGLE",
                "category": "Station ID",
                "description": "Uploaded from Live Assist",
                "priority": "5",
                "cooldown_seconds": "10",
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Browser Jingle"
    assert body["asset_type"] == "JINGLE"
    assert body["duration"] > 0
    assert Path(body["file_path"]).exists()


def test_browser_asset_upload_rejects_invalid_audio(client, tmp_path):
    path = tmp_path / "broken.mp3"
    path.write_bytes(b"not real audio")
    with path.open("rb") as fh:
        response = client.post(
            "/api/assets/upload",
            files={"file": (path.name, fh, "audio/mpeg")},
            data={"name": "Broken Ad", "asset_type": "ADVERTISEMENT"},
        )

    assert response.status_code == 400
    assert "" != response.json()["detail"]
