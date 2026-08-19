"""
app/services/playback_history.py

V0.8 Part 3 — real playback history recorder.

It subscribes to the existing shared AudioEngine. No second player/engine is
created. It records the actual file loaded/played and closes that history row
on the real AudioEngine track-end event.
"""

from __future__ import annotations

import datetime
import os
import threading
from typing import Optional

from sqlalchemy import func, select
from src.engine import AudioEngine
from src.models import PlayerState, TrackEndReason

from ..database.database import session_scope
from ..database.models import Asset, Song
from ..database.playback_history_models import PlaybackHistory


class PlaybackHistoryRecorder:
    def __init__(self, engine: AudioEngine) -> None:
        self._engine = engine
        self._lock = threading.RLock()
        self._active_history_id: Optional[int] = None
        self._active_file_path: Optional[str] = None
        self._running = False

        self._engine.on_state_change(self._on_state_change)
        self._engine.on_track_end(self._on_track_end)
        self._running = True

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            self._active_history_id = None
            self._active_file_path = None

    def _resolve_content(self, db, file_path: str) -> tuple[str, Optional[int], str]:
        normalized = os.path.normcase(os.path.abspath(file_path))

        song = db.execute(
            select(Song).where(Song.file_path == file_path)
        ).scalar_one_or_none()
        if song is None:
            song = db.execute(
                select(Song).where(func.lower(Song.file_path) == normalized.lower())
            ).scalar_one_or_none()

        if song is not None:
            name = song.title or os.path.basename(file_path)
            if song.artist:
                name = f"{name} — {song.artist}"
            return "SONG", song.id, name

        asset = db.execute(
            select(Asset).where(Asset.file_path == file_path)
        ).scalar_one_or_none()
        if asset is None:
            asset = db.execute(
                select(Asset).where(func.lower(Asset.file_path) == normalized.lower())
            ).scalar_one_or_none()

        if asset is not None:
            return str(asset.asset_type.value if hasattr(asset.asset_type, "value") else asset.asset_type), asset.id, asset.name

        return "AUDIO", None, os.path.basename(file_path)

    def _on_state_change(self, old_state: PlayerState, new_state: PlayerState) -> None:
        with self._lock:
            if not self._running or new_state != PlayerState.PLAYING:
                return

        status = self._engine.get_status()
        file_path = status.file_path
        if not file_path:
            return

        with self._lock:
            if self._active_history_id is not None and self._active_file_path == file_path:
                return

        now = datetime.datetime.utcnow()

        try:
            with session_scope() as db:
                content_type, content_id, content_name = self._resolve_content(db, file_path)
                row = PlaybackHistory(
                    started_at=now,
                    content_type=content_type,
                    content_id=content_id,
                    content_name=content_name,
                    file_path=file_path,
                    duration_seconds=float(status.duration_seconds or 0.0),
                    status="PLAYING",
                    source="ENGINE",
                )
                db.add(row)
                db.flush()
                history_id = row.id

            with self._lock:
                self._active_history_id = history_id
                self._active_file_path = file_path
        except Exception:
            # History must never break audio playback.
            return

    def _on_track_end(self, reason: TrackEndReason) -> None:
        with self._lock:
            history_id = self._active_history_id
            self._active_history_id = None
            self._active_file_path = None
            running = self._running

        if not running or history_id is None:
            return

        now = datetime.datetime.utcnow()
        if reason == TrackEndReason.COMPLETED:
            final_status = "COMPLETED"
        elif reason == TrackEndReason.MANUAL_STOP:
            final_status = "SKIPPED"
        else:
            final_status = "FAILED"

        error = None if final_status != "FAILED" else "AudioEngine playback error"

        try:
            with session_scope() as db:
                row = db.get(PlaybackHistory, history_id)
                if row is not None:
                    row.ended_at = now
                    row.status = final_status
                    row.error_message = error
        except Exception:
            return


def list_history(
    db,
    *,
    date: Optional[datetime.date] = None,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PlaybackHistory]:
    stmt = select(PlaybackHistory).order_by(PlaybackHistory.started_at.desc())
    if date is not None:
        start = datetime.datetime.combine(date, datetime.time.min)
        end = start + datetime.timedelta(days=1)
        stmt = stmt.where(
            PlaybackHistory.started_at >= start,
            PlaybackHistory.started_at < end,
        )
    if content_type:
        stmt = stmt.where(PlaybackHistory.content_type == content_type)
    if status:
        stmt = stmt.where(PlaybackHistory.status == status)

    return list(db.execute(stmt.limit(limit).offset(offset)).scalars())


def get_summary(db, *, date: Optional[datetime.date] = None) -> dict:
    rows = list_history(db, date=date, limit=10000)

    summary = {
        "total": len(rows),
        "songs_played": 0,
        "jingles_played": 0,
        "advertisements_played": 0,
        "failures": 0,
        "skipped": 0,
        "completed": 0,
        "total_duration_seconds": 0.0,
    }

    for row in rows:
        if row.status == "COMPLETED":
            summary["completed"] += 1
        elif row.status == "FAILED":
            summary["failures"] += 1
        elif row.status == "SKIPPED":
            summary["skipped"] += 1

        if row.status == "COMPLETED":
            summary["total_duration_seconds"] += float(row.duration_seconds or 0)

        if row.content_type == "SONG":
            summary["songs_played"] += 1
        elif row.content_type == "JINGLE":
            summary["jingles_played"] += 1
        elif row.content_type == "ADVERTISEMENT":
            summary["advertisements_played"] += 1

    return summary
