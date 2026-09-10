"""PyInstaller launcher for Super Station Studio backend."""
from __future__ import annotations

import os

import uvicorn

# Import the FastAPI application directly.  Do not pass "app.main:app" as a
# string here: PyInstaller cannot reliably discover that dynamic import, which
# causes packaged builds to fail with ModuleNotFoundError: app.
from app.main import app


DEFAULT_PORT = 8000


def _port() -> int:
    raw = os.environ.get("SSS_BACKEND_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid SSS_BACKEND_PORT: {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise SystemExit(f"SSS_BACKEND_PORT must be between 1 and 65535, got {port}")
    return port


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=_port(),
        reload=False,
    )
