"""
app/api/reports.py

V0.8 Part 3 — real playback reports/history endpoints.
"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Song
from ..services.playback_history import get_summary, list_history

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/playback")
def playback_report(
    date: Optional[datetime.date] = Query(None),
    content_type: Optional[str] = Query(None, pattern="^(SONG|JINGLE|ADVERTISEMENT|AUDIO)$"),
    status: Optional[str] = Query(None, pattern="^(PLAYING|COMPLETED|SKIPPED|FAILED)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    rows = list_history(
        db,
        date=date,
        content_type=content_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [row.to_dict() for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/recently-played")
def recently_played(
    limit: int = Query(6, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """Return the latest real song playback events for the dashboard.

    Only terminal playback rows are returned, so the currently playing track
    never appears as "recently played" until it has actually ended or been
    skipped. Song metadata is resolved from the library to provide a clean
    title/artist pair to the frontend.
    """
    rows = list_history(db, content_type="SONG", limit=limit * 2)
    items = []
    for row in rows:
        if row.status == "PLAYING":
            continue
        artist = ""
        title = row.content_name or "Unknown track"
        if row.content_id is not None:
            song = db.get(Song, row.content_id)
            if song is not None:
                title = song.title or title
                artist = song.artist or ""
        if not artist and " — " in title:
            title, artist = title.split(" — ", 1)
        items.append({
            "id": row.id,
            "title": title,
            "artist": artist,
            "duration_seconds": round(float(row.duration_seconds or 0.0), 3),
            "played_at": row.started_at.isoformat() if row.started_at else None,
            "status": row.status,
            "source": row.source,
        })
        if len(items) >= limit:
            break
    return {"items": items}


@router.get("/summary")
def report_summary(
    date: Optional[datetime.date] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return get_summary(db, date=date)
