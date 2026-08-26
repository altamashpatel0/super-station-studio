from pathlib import Path

from fastapi.testclient import TestClient


def test_music_import_route_exists(client):
    response = client.post(
        "/api/library/import-files",
        files=[
            ("files", ("track.txt", b"not-audio", "text/plain")),
        ],
    )
    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]
