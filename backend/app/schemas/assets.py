"""
app/schemas/assets.py
=======================

Pydantic request/response models for the Jingle & Advertisement
Library API. Mirrors the split used by `schemas/library.py` /
`schemas/playlist.py`: wire formats kept independent of the
SQLAlchemy models in `database/models.py`.

V0.5 Part 2 adds two playback-management fields, `priority` and
`cooldown_seconds`:

  - Both are optional on import (default 0/0) and optional on update
    (only-provided-fields-change, same convention as the rest of
    `AssetUpdate`).
  - `cooldown_seconds` is validated as >= 0 at the schema layer (a
    negative value never reaches the service/repository).
  - `file_path`, `asset_type`, and `duration` remain untouched -
    still not editable via `AssetUpdate`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AssetImportRequest(BaseModel):
    """Import an existing audio file on disk as a Jingle/Advertisement asset."""

    file_path: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)
    asset_type: str = Field(..., pattern="^(JINGLE|ADVERTISEMENT)$")
    category: str = ""
    description: str = ""
    priority: int = 0
    cooldown_seconds: int = Field(0, ge=0)


class AssetUpdate(BaseModel):
    """All fields optional - only provided fields are changed.
    `file_path`/`asset_type`/`duration` are not editable here."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    cooldown_seconds: Optional[int] = Field(None, ge=0)


class AssetOut(BaseModel):
    id: int
    name: str
    asset_type: str
    file_path: str
    duration: float
    category: str
    description: str
    enabled: bool
    priority: int
    cooldown_seconds: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
