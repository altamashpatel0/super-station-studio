"""
app/main.py
============

FastAPI application entry point for Super Station Studio V0.2.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import library, playback
from .api.engine_provider import shutdown_engine
from .database.database import init_db

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    shutdown_engine()


app = FastAPI(
    title="Super Station Studio API",
    description="Radio automation & playout backend - V0.2 (Music Library)",
    version="0.2.0",
    lifespan=lifespan,
)

# Local Electron/React dev servers only; tighten this before any
# non-local deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "app://."],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(library.router)
app.include_router(playback.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "0.2.0"}
