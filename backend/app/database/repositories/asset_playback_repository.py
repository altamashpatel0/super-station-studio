from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssetPlaybackState


class AssetPlaybackRepository:
    """Persistence layer for per-asset playback state."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_asset_id(
        self,
        asset_id: int,
    ) -> Optional[AssetPlaybackState]:
        stmt = select(AssetPlaybackState).where(
            AssetPlaybackState.asset_id == asset_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_or_create(
        self,
        asset_id: int,
    ) -> AssetPlaybackState:
        state = self.get_by_asset_id(asset_id)

        if state is None:
            state = AssetPlaybackState(asset_id=asset_id)
            self.db.add(state)
            self.db.flush()

        return state

    def mark_started(
        self,
        asset_id: int,
        when: datetime.datetime,
    ) -> AssetPlaybackState:
        state = self.get_or_create(asset_id)

        state.state = "PLAYING"
        state.started_at = when
        state.last_played_at = when

        state.completed_at = None
        state.failed_at = None
        state.stopped_at = None
        state.last_error = None

        state.play_count += 1

        self.db.flush()
        return state

    def mark_completed(
        self,
        asset_id: int,
        when: datetime.datetime,
    ) -> AssetPlaybackState:
        state = self.get_or_create(asset_id)

        state.state = "COMPLETED"
        state.completed_at = when
        state.last_error = None

        self.db.flush()
        return state

    def mark_stopped(
        self,
        asset_id: int,
        when: datetime.datetime,
    ) -> AssetPlaybackState:
        state = self.get_or_create(asset_id)

        state.state = "STOPPED"
        state.stopped_at = when

        self.db.flush()
        return state

    def mark_failed(
        self,
        asset_id: int,
        when: datetime.datetime,
        error: str,
    ) -> AssetPlaybackState:
        state = self.get_or_create(asset_id)

        state.state = "FAILED"
        state.failed_at = when
        state.last_error = error

        self.db.flush()
        return state