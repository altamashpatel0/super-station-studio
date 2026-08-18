from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import (
    Asset,
    AssetPlaybackState,
    AssetType,
    Playlist,
    PlaylistTrack,
    Schedule,
    Song,
)
from ..database.repositories.asset_playback_repository import AssetPlaybackRepository
from .clock_wheel import ClockWheel


class SelectionError(Exception):
    """Base domain error for scheduler selection."""


class ScheduleSelectionNotFoundError(SelectionError):
    pass


class UnsupportedTargetTypeError(SelectionError):
    pass


class TargetNotFoundError(SelectionError):
    pass


class TargetDisabledError(SelectionError):
    pass


class TargetFileMissingError(SelectionError):
    pass


class WrongAssetTypeError(SelectionError):
    pass


class CooldownBlockedError(SelectionError):
    pass


class NoEligiblePlaylistTrackError(SelectionError):
    pass


@dataclass(frozen=True)
class SelectionResult:
    schedule_id: int
    target_type: str
    target_id: int
    selected_id: int
    selected_name: str
    selected_file_path: str
    selected_duration: float
    selected_kind: str

    def to_dict(self) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "selected_id": self.selected_id,
            "selected_name": self.selected_name,
            "selected_file_path": self.selected_file_path,
            "selected_duration": self.selected_duration,
            "selected_kind": self.selected_kind,
        }


def _target_type(schedule: Schedule) -> str:
    value = schedule.target_type
    return value.value if hasattr(value, "value") else str(value)


def _file_exists(path: str) -> bool:
    return bool(path) and Path(path).is_file()


def _asset_cooldown_active(
    db: Session,
    asset: Asset,
    now: datetime,
) -> bool:
    cooldown = int(asset.cooldown_seconds or 0)
    if cooldown <= 0:
        return False

    state = AssetPlaybackRepository(db).get_by_asset_id(asset.id)
    if state is None or state.last_played_at is None:
        return False

    return (now - state.last_played_at).total_seconds() < cooldown


def _asset_result(schedule: Schedule, asset: Asset) -> SelectionResult:
    kind = asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type)
    return SelectionResult(
        schedule_id=schedule.id,
        target_type=kind,
        target_id=schedule.target_id,
        selected_id=asset.id,
        selected_name=asset.name,
        selected_file_path=asset.file_path,
        selected_duration=float(asset.duration or 0.0),
        selected_kind=kind,
    )


def _song_result(schedule: Schedule, song: Song, kind: str = "SONG") -> SelectionResult:
    return SelectionResult(
        schedule_id=schedule.id,
        target_type=_target_type(schedule),
        target_id=schedule.target_id,
        selected_id=song.id,
        selected_name=song.title,
        selected_file_path=song.file_path,
        selected_duration=float(song.duration or 0.0),
        selected_kind=kind,
    )


def _select_song(db: Session, schedule: Schedule) -> SelectionResult:
    song = db.get(Song, schedule.target_id)
    if song is None:
        raise TargetNotFoundError(f"No song with id {schedule.target_id}.")
    if not song.enabled:
        raise TargetDisabledError(f"Song {song.id} is disabled.")
    if not _file_exists(song.file_path):
        raise TargetFileMissingError(
            f"Song {song.id} file does not exist: {song.file_path}"
        )
    return _song_result(schedule, song)


def _select_asset(
    db: Session,
    schedule: Schedule,
    expected_type: AssetType,
    now: datetime,
) -> SelectionResult:
    asset = db.get(Asset, schedule.target_id)
    if asset is None:
        raise TargetNotFoundError(f"No asset with id {schedule.target_id}.")

    actual = asset.asset_type if isinstance(asset.asset_type, AssetType) else AssetType(str(asset.asset_type))
    if actual != expected_type:
        raise WrongAssetTypeError(
            f"Asset {asset.id} is {actual.value}, not {expected_type.value}."
        )
    if not asset.enabled:
        raise TargetDisabledError(f"Asset {asset.id} is disabled.")
    if not _file_exists(asset.file_path):
        raise TargetFileMissingError(
            f"Asset {asset.id} file does not exist: {asset.file_path}"
        )
    if _asset_cooldown_active(db, asset, now):
        raise CooldownBlockedError(f"Asset {asset.id} is on cooldown.")

    return _asset_result(schedule, asset)


def _select_playlist(db: Session, schedule: Schedule) -> SelectionResult:
    playlist = db.get(Playlist, schedule.target_id)
    if playlist is None:
        raise TargetNotFoundError(f"No playlist with id {schedule.target_id}.")

    stmt = (
        select(PlaylistTrack)
        .join(PlaylistTrack.song)
        .where(
            PlaylistTrack.playlist_id == playlist.id,
            Song.enabled.is_(True),
        )
        .order_by(PlaylistTrack.position.asc(), PlaylistTrack.id.asc())
    )
    tracks = db.execute(stmt).scalars().all()

    for track in tracks:
        if track.song is not None and _file_exists(track.song.file_path):
            return _song_result(schedule, track.song, "PLAYLIST_TRACK")

    raise NoEligiblePlaylistTrackError(
        f"Playlist {playlist.id} has no eligible tracks."
    )


def select_for_schedule(
    db: Session,
    schedule_id: int,
    now: Optional[datetime] = None,
) -> SelectionResult:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise ScheduleSelectionNotFoundError(
            f"No schedule with id {schedule_id}."
        )
    if not schedule.enabled:
        raise TargetDisabledError(f"Schedule {schedule.id} is disabled.")

    current_time = now or datetime.now()
    target = _target_type(schedule)

    if target == "SONG":
        return _select_song(db, schedule)
    if target == "JINGLE":
        return _select_asset(db, schedule, AssetType.JINGLE, current_time)
    if target == "ADVERTISEMENT":
        return _select_asset(db, schedule, AssetType.ADVERTISEMENT, current_time)
    if target == "PLAYLIST":
        return _select_playlist(db, schedule)

    raise UnsupportedTargetTypeError(f"Unsupported target_type '{target}'.")


def select_for_current_schedule(
    db: Session,
    now: datetime,
) -> Optional[SelectionResult]:
    occurrence = ClockWheel(db).get_current_schedule(now)
    if occurrence is None:
        return None
    return select_for_schedule(db, occurrence.schedule_id, now=now)
