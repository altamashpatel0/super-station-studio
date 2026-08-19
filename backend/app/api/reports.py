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


@router.get("/summary")
def report_summary(
    date: Optional[datetime.date] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return get_summary(db, date=date)
