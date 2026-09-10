from __future__ import annotations

import datetime
import os
import threading
from typing import Optional

from sqlalchemy.orm import Session

from src.engine import AudioEngine
from src.models import AudioEngineError, TrackEndReason

from .playback_controller import PlaybackController, PlaybackSource

from ..database.database import session_scope
from ..database.models import Asset, AssetPlaybackState
from ..database.repositories.asset_repository import (
    AssetNotFoundError,
    AssetRepository,
)
from ..database.repositories.asset_playback_repository import (
    AssetPlaybackRepository,
)


class AssetPlaybackError(Exception):
    """Base class for asset playback validation/runtime errors."""


class AssetPlaybackFileError(AssetPlaybackError):
    """Raised when the asset's audio file is missing."""


class AssetCooldownError(AssetPlaybackError):
    """Raised when an asset is still inside its cooldown window."""

    def __init__(self, remaining_seconds: float) -> None:
        self.remaining_seconds = max(0.0, remaining_seconds)

        super().__init__(
            f"Asset is on cooldown for "
            f"{self.remaining_seconds:.1f} more seconds."
        )


class AssetPlaybackManager:
    """
    Integrates Jingle/Advertisement assets with the existing shared
    AudioEngine.

    This class does NOT implement a second audio engine.
    """

    def __init__(
        self,
        engine: AudioEngine,
        controller: Optional[PlaybackController] = None,
    ) -> None:
        self._engine = engine
        self._controller = controller

        self._lock = threading.RLock()

        self._active_asset_id: Optional[int] = None
        self._pending_asset_id: Optional[int] = None

        # IMPORTANT:
        # This manager must be registered before QueueManager so that
        # COMPLETED is recorded before QueueManager auto-loads the next song.
        self._engine.on_state_change(self._on_state_change)
        self._engine.on_track_end(self._on_track_end)

    @property
    def engine(self) -> AudioEngine:
        return self._engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_asset(
        self,
        db: Session,
        asset_id: int,
        source: PlaybackSource = PlaybackSource.ASSET,
    ) -> dict:

        asset = AssetRepository(db).get_by_id(asset_id)

        if asset is None:
            raise AssetNotFoundError(
                f"No asset with id {asset_id}."
            )

        if not asset.enabled:
            raise AssetPlaybackError(
                "This asset is disabled."
            )

        if not os.path.isfile(asset.file_path):
            raise AssetPlaybackFileError(
                f"Audio file not found: {asset.file_path}"
            )

        state_repo = AssetPlaybackRepository(db)
        state = state_repo.get_by_asset_id(asset.id)

        now = datetime.datetime.utcnow()

        # --------------------------------------------------------------
        # Cooldown
        # --------------------------------------------------------------

        if (
            state is not None
            and state.last_played_at is not None
            and asset.cooldown_seconds > 0
        ):
            elapsed = (
                now - state.last_played_at
            ).total_seconds()

            remaining = (
                asset.cooldown_seconds - elapsed
            )

            if remaining > 0:
                raise AssetCooldownError(remaining)

        # --------------------------------------------------------------
        # Replace currently playing asset, if any
        # --------------------------------------------------------------

        with self._lock:

            if (
                self._active_asset_id is not None
                and self._active_asset_id != asset.id
            ):
                previous_id = self._active_asset_id

                state_repo.mark_stopped(
                    previous_id,
                    now,
                )

                self._active_asset_id = None

                db.commit()

            self._pending_asset_id = asset.id
            self._active_asset_id = asset.id

        # --------------------------------------------------------------
        # Load + play through the EXISTING AudioEngine
        # --------------------------------------------------------------

        try:
            # PlaybackController can synchronously notify QueueManager while
            # replacing the current source. Release any request-scoped DB
            # transaction before entering the audio operation so the callback
            # can write through its own session without SQLite lock contention.
            db.commit()
            if self._controller is not None:
                status = self._controller.start_track(
                    source,
                    asset.file_path,
                )
            else:
                self._engine.load_track(asset.file_path)
                status = self._engine.play()

        except Exception as exc:

            with self._lock:

                if self._active_asset_id == asset.id:
                    self._active_asset_id = None

                self._pending_asset_id = None

            state_repo.mark_failed(
                asset.id,
                datetime.datetime.utcnow(),
                str(exc),
            )

            db.commit()

            raise

        # --------------------------------------------------------------
        # Successful playback start
        # --------------------------------------------------------------

        with self._lock:
            self._pending_asset_id = None

        started_at = datetime.datetime.utcnow()

        state = state_repo.mark_started(
            asset.id,
            started_at,
        )

        db.commit()

        return self._response(
            asset,
            state,
            status.to_dict(),
        )

    def get_status(
        self,
        db: Session,
        asset_id: int,
    ) -> dict:

        asset = AssetRepository(db).get_by_id(asset_id)

        if asset is None:
            raise AssetNotFoundError(
                f"No asset with id {asset_id}."
            )

        state = (
            AssetPlaybackRepository(db)
            .get_by_asset_id(asset_id)
        )

        engine_status = None

        with self._lock:
            is_active = (
                self._active_asset_id == asset_id
            )

        if is_active:
            engine_status = (
                self._engine
                .get_status()
                .to_dict()
            )

        return self._response(
            asset,
            state,
            engine_status,
        )

    # ------------------------------------------------------------------
    # Response
    # ------------------------------------------------------------------

    def _response(
        self,
        asset: Asset,
        state: Optional[AssetPlaybackState],
        engine_status: Optional[dict],
    ) -> dict:

        now = datetime.datetime.utcnow()

        remaining = 0.0

        if (
            state is not None
            and state.last_played_at is not None
            and asset.cooldown_seconds > 0
        ):
            remaining = max(
                0.0,
                asset.cooldown_seconds
                - (
                    now - state.last_played_at
                ).total_seconds(),
            )

        asset_type = (
            asset.asset_type.value
            if hasattr(asset.asset_type, "value")
            else asset.asset_type
        )

        return {
            "asset_id": asset.id,
            "name": asset.name,
            "asset_type": asset_type,

            "state": (
                state.state
                if state is not None
                else "IDLE"
            ),

            "started_at": (
                state.started_at.isoformat()
                if state and state.started_at
                else None
            ),

            "last_played_at": (
                state.last_played_at.isoformat()
                if state and state.last_played_at
                else None
            ),

            "completed_at": (
                state.completed_at.isoformat()
                if state and state.completed_at
                else None
            ),

            "failed_at": (
                state.failed_at.isoformat()
                if state and state.failed_at
                else None
            ),

            "stopped_at": (
                state.stopped_at.isoformat()
                if state and state.stopped_at
                else None
            ),

            "last_error": (
                state.last_error
                if state
                else None
            ),

            "play_count": (
                state.play_count
                if state
                else 0
            ),

            "cooldown_seconds": (
                asset.cooldown_seconds
            ),

            "cooldown_remaining_seconds": round(
                remaining,
                3,
            ),

            "engine_status": engine_status,
        }

    # ------------------------------------------------------------------
    # AudioEngine event hooks
    # ------------------------------------------------------------------

    def _on_state_change(
        self,
        old_state,
        new_state,
    ) -> None:

        if new_state.value != "LOADING":
            return

        with self._lock:
            active_id = self._active_asset_id
            pending_id = self._pending_asset_id

        # Loading our own asset must not mark it stopped.
        if (
            active_id is None
            or active_id == pending_id
        ):
            return

        # Another consumer (Music Library / Queue) is loading
        # a new track. V0.1's Player.load() stops the old output
        # without emitting MANUAL_STOP.
        try:
            with session_scope() as db:
                AssetPlaybackRepository(
                    db
                ).mark_stopped(
                    active_id,
                    datetime.datetime.utcnow(),
                )

        finally:
            with self._lock:
                if self._active_asset_id == active_id:
                    self._active_asset_id = None

    def _on_track_end(
        self,
        reason: TrackEndReason,
    ) -> None:

        with self._lock:
            asset_id = self._active_asset_id

            if asset_id is None:
                return

            self._active_asset_id = None
            self._pending_asset_id = None

        try:

            with session_scope() as db:

                repo = AssetPlaybackRepository(db)
                now = datetime.datetime.utcnow()

                if reason == TrackEndReason.COMPLETED:

                    repo.mark_completed(
                        asset_id,
                        now,
                    )

                elif reason == TrackEndReason.MANUAL_STOP:

                    repo.mark_stopped(
                        asset_id,
                        now,
                    )

                elif reason == TrackEndReason.ERROR:

                    repo.mark_failed(
                        asset_id,
                        now,
                        "Audio engine playback error.",
                    )

        except Exception:
            # Playback callbacks must NEVER break the audio engine.
            pass