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


def _local_day_bounds_as_utc_naive(date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Convert the operator's local calendar day into UTC-naive DB bounds."""
    local_tz = datetime.datetime.now().astimezone().tzinfo
    local_start = datetime.datetime.combine(date, datetime.time.min, tzinfo=local_tz)
    local_end = local_start + datetime.timedelta(days=1)
    utc = datetime.timezone.utc
    return (
        local_start.astimezone(utc).replace(tzinfo=None),
        local_end.astimezone(utc).replace(tzinfo=None),
    )


class PlaybackHistoryRecorder:
    def __init__(self, engine: AudioEngine) -> None:
        self._engine = engine
        self._lock = threading.RLock()
        self._active_history_id: Optional[int] = None
        self._active_file_path: Optional[str] = None
        self._running = False

        self._engine.on_state_change(self._on_state_change)
        self._engine.on_track_end(self._on_track_end)
        self._reconcile_open_rows()
        self._running = True

    def _reconcile_open_rows(self) -> None:
        """Close stale PLAYING rows left behind by an earlier process run.

        The AudioEngine is created fresh when FastAPI starts, so a persisted
        PLAYING row from a previous process cannot still represent live audio.
        Treat it as skipped rather than leaving a permanent PLAYING entry.
        """
        now = datetime.datetime.utcnow()
        try:
            with session_scope() as db:
                rows = list(
                    db.execute(
                        select(PlaybackHistory).where(PlaybackHistory.status == "PLAYING")
                    ).scalars()
                )
                for row in rows:
                    row.ended_at = now
                    row.status = "SKIPPED"
                    row.error_message = "Playback session ended when the station backend restarted."
                    if row.started_at:
                        elapsed = max(0.0, (now - row.started_at).total_seconds())
                        if row.duration_seconds > 0:
                            row.duration_seconds = min(float(row.duration_seconds), elapsed)
                        else:
                            row.duration_seconds = elapsed
        except Exception:
            # History cleanup must never prevent the station from starting.
            return

    def _finish_history_row(
        self,
        history_id: int,
        final_status: str,
        now: datetime.datetime,
        error: Optional[str] = None,
    ) -> None:
        """Persist the terminal state and the actual elapsed play time."""
        with session_scope() as db:
            row = db.get(PlaybackHistory, history_id)
            if row is None:
                return
            row.ended_at = now
            row.status = final_status
            row.error_message = error
            if row.started_at:
                elapsed = max(0.0, (now - row.started_at).total_seconds())
                if final_status in {"SKIPPED", "FAILED"}:
                    row.duration_seconds = elapsed
                elif row.duration_seconds <= 0:
                    row.duration_seconds = elapsed
                else:
                    row.duration_seconds = min(float(row.duration_seconds), elapsed)

    def _close_active_as_replaced(self, now: datetime.datetime, reason: str) -> None:
        """Close the current history row when another file replaces it.

        `AudioEngine.load_track()` stops the underlying output before loading
        the next file, but the V0.1 engine deliberately does not emit a
        MANUAL_STOP event for that replacement. This is the exact path that
        previously left skipped tracks stuck at PLAYING in Reports & Logs.
        """
        with self._lock:
            history_id = self._active_history_id
            self._active_history_id = None
            self._active_file_path = None

        if history_id is None:
            return

        try:
            self._finish_history_row(history_id, "SKIPPED", now, reason)
        except Exception:
            return

    def finish_active_as_skipped(self, reason: str) -> None:
        """Close the current history row when a bounded schedule window ends.

        A schedule can intentionally end in the middle of a track. The audio
        engine is paused at that boundary rather than naturally completing the
        file, so the history row must be finalized explicitly.
        """
        now = datetime.datetime.utcnow()
        with self._lock:
            history_id = self._active_history_id
            self._active_history_id = None
            self._active_file_path = None
        if history_id is None:
            return
        try:
            self._finish_history_row(history_id, "SKIPPED", now, reason)
        except Exception:
            # History must never interfere with the scheduler boundary.
            return

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
            if not self._running:
                return

        # Replacing a playing file with load_track() transitions the engine
        # PLAYING -> LOADING without emitting on_track_end(). Close that
        # history row explicitly so manual Next/Skip and asset/song switches
        # are recorded as SKIPPED instead of remaining PLAYING forever.
        if old_state == PlayerState.PLAYING and new_state in {PlayerState.LOADING, PlayerState.ERROR}:
            self._close_active_as_replaced(
                datetime.datetime.utcnow(),
                "Playback was replaced before the item completed.",
            )

        if new_state != PlayerState.PLAYING:
            return

        status = self._engine.get_status()
        file_path = status.file_path
        if not file_path:
            return

        now = datetime.datetime.utcnow()

        with self._lock:
            active_id = self._active_history_id
            active_path = self._active_file_path

        # Defensive guard for engines/callers that change files without the
        # intermediate state callback reaching us.
        if active_id is not None and active_path != file_path:
            self._close_active_as_replaced(
                now,
                "Playback was replaced before the item completed.",
            )

        with self._lock:
            if self._active_history_id is not None and self._active_file_path == file_path:
                return

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
            error = None
        elif reason == TrackEndReason.MANUAL_STOP:
            final_status = "SKIPPED"
            error = None
        else:
            final_status = "FAILED"
            error = "AudioEngine playback error"

        try:
            self._finish_history_row(history_id, final_status, now, error)
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
        start, end = _local_day_bounds_as_utc_naive(date)
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
