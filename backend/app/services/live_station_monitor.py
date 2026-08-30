"""
app/services/live_station_monitor.py
====================================

V0.8 Part 1 — real live station snapshot.

This service is read-only. It never starts/stops playback and never creates
another AudioEngine. It reads the existing V0.7 StationRuntime, the shared
AudioEngine status, and the existing database queue/library state.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.orm import Session

from ..database.models import QueueItemStatus
from ..database.repositories.asset_repository import AssetRepository
from ..database.repositories.queue_repository import QueueRepository
from ..database.repositories.song_repository import SongRepository


class LiveStationMonitor:
    """Build a single JSON-safe snapshot for the V0.8 Live Monitor UI."""

    MAX_NEXT_ITEMS = 5

    def snapshot(self, db: Session, station_runtime: Any) -> dict:
        # PlaybackController is the production playback authority. Fall back
        # to the legacy runtime engine for isolated tests/compatibility.
        try:
            from ..api.playback_controller_provider import get_playback_controller
            engine_status = get_playback_controller().get_status()
        except Exception:
            engine_status = station_runtime.runtime.engine.get_status().to_dict()

        current = self._resolve_current(
            db,
            engine_status.get("file_path"),
            engine_status,
        )
        next_items, queued_count = self._next_up(db)

        watchdog = station_runtime.watchdog
        worker = station_runtime.worker
        runtime = station_runtime.runtime
        recovery = station_runtime.recovery
        continuation = station_runtime.continuation

        watchdog_status = (
            watchdog.status.value
            if hasattr(watchdog.status, "value")
            else str(watchdog.status)
        )

        overall = self._overall_health(
            station_running=station_runtime.is_running,
            worker_running=worker.is_running,
            watchdog_status=watchdog_status,
            scheduler_error=runtime.get_last_error(),
            worker_error=worker.last_error,
            recovery_error=recovery.last_error,
            watchdog_error=watchdog.last_recovery_error,
        )

        selection = runtime.get_last_selection()
        selection_data = selection.to_dict() if selection is not None else None

        state = str(engine_status.get("state") or "IDLE").upper()
        station_status = {
            "mode": (
                "ON_AIR"
                if state == "PLAYING"
                else "PAUSED"
                if state == "PAUSED"
                else "OFF_AIR"
            ),
            "player_state": state,
            "runtime_running": bool(station_runtime.is_running),
        }

        return {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            # Authoritative master volume from the same playback controller
            # used by /api/live-assist/volume. Keep it at the live snapshot
            # level so the UI does not fall back to 100% on every poll.
            "volume": round(float(engine_status.get("volume") or 0.0), 3),
            "station": station_status,
            "now_playing": current,
            "next_up": next_items,
            "queue": {
                "queued_count": queued_count,
                "preview_count": len(next_items),
                "preview_limit": self.MAX_NEXT_ITEMS,
            },
            "health": {
                "overall": overall,
                "station_runtime": "RUNNING" if station_runtime.is_running else "STOPPED",
                "automation_worker": "RUNNING" if worker.is_running else "STOPPED",
                "playback_continuation": "ATTACHED" if continuation.running else "DETACHED",
                "watchdog": watchdog_status,
                "watchdog_recoveries": watchdog.recovery_count,
                "scheduler_last_error": runtime.get_last_error(),
                "worker_last_error": worker.last_error,
                "recovery_last_error": recovery.last_error,
                "watchdog_last_error": watchdog.last_recovery_error,
            },
            "scheduler": {
                "last_selection": selection_data,
            },
        }

    @staticmethod
    def _overall_health(
        *,
        station_running: bool,
        worker_running: bool,
        watchdog_status: str,
        scheduler_error: str | None,
        worker_error: str | None,
        recovery_error: str | None,
        watchdog_error: str | None,
    ) -> str:
        if not station_running or not worker_running:
            return "DEGRADED"

        if watchdog_status in {"STALLED", "RECOVERING"}:
            return "DEGRADED"

        if any((scheduler_error, worker_error, recovery_error, watchdog_error)):
            return "DEGRADED"

        return "HEALTHY"

    def _resolve_current(
        self,
        db: Session,
        file_path: str | None,
        engine_status: dict,
    ) -> dict | None:
        if not file_path:
            return None

        song = SongRepository(db).get_by_path(file_path)
        if song is not None:
            return {
                "kind": "SONG",
                "id": song.id,
                "title": song.title,
                "artist": song.artist,
                "album": song.album,
                "duration_seconds": round(
                    float(engine_status.get("duration_seconds") or song.duration or 0.0),
                    3,
                ),
                "position_seconds": round(
                    float(engine_status.get("position_seconds") or 0.0),
                    3,
                ),
                "state": str(engine_status.get("state") or "IDLE").upper(),
            }

        asset = AssetRepository(db).get_by_path(file_path)
        if asset is not None:
            asset_type = (
                asset.asset_type.value
                if hasattr(asset.asset_type, "value")
                else str(asset.asset_type)
            )
            return {
                "kind": asset_type,
                "id": asset.id,
                "title": asset.name,
                "artist": None,
                "album": None,
                "duration_seconds": round(
                    float(engine_status.get("duration_seconds") or asset.duration or 0.0),
                    3,
                ),
                "position_seconds": round(
                    float(engine_status.get("position_seconds") or 0.0),
                    3,
                ),
                "state": str(engine_status.get("state") or "IDLE").upper(),
            }

        # The file is genuinely loaded by the real engine but is no longer
        # represented in either library table. Do not invent metadata.
        return {
            "kind": "UNKNOWN",
            "id": None,
            "title": None,
            "artist": None,
            "album": None,
            "duration_seconds": round(float(engine_status.get("duration_seconds") or 0.0), 3),
            "position_seconds": round(float(engine_status.get("position_seconds") or 0.0), 3),
            "state": str(engine_status.get("state") or "IDLE").upper(),
        }

    def _next_up(self, db: Session) -> tuple[list[dict], int]:
        items = QueueRepository(db).list_all()
        result: list[dict] = []
        queued_count = 0

        for item in items:
            status = (
                item.status.value
                if isinstance(item.status, QueueItemStatus)
                else str(item.status)
            )
            if status != QueueItemStatus.QUEUED.value:
                continue

            queued_count += 1
            song = item.song
            if song is None:
                continue

            result.append(
                {
                    "queue_item_id": item.id,
                    "position": item.position,
                    "kind": "SONG",
                    "id": song.id,
                    "title": song.title,
                    "artist": song.artist,
                    "album": song.album,
                    "duration_seconds": round(float(song.duration or 0.0), 3),
                }
            )

            if len(result) >= self.MAX_NEXT_ITEMS:
                # Continue counting real queued items only when needed?
                # We need the exact queue count, so do not break early.
                continue

        return result, queued_count
