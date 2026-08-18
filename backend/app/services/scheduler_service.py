from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from ..database.models import Asset, AssetType, Playlist, Schedule, Song
from ..database.repositories.schedule_repository import (
    ScheduleNotFoundError,
    ScheduleRepository,
)
from ..schemas.scheduler import ScheduleCreate, ScheduleUpdate


class InvalidScheduleError(Exception):
    """Raised when a schedule is invalid for current database state."""


def _canonical_days(days: list[int]) -> str:
    return "," + ",".join(str(day) for day in sorted(days)) + ","


def _validate_target(db: Session, target_type: str, target_id: int) -> None:
    if target_type == "SONG":
        if db.get(Song, target_id) is None:
            raise InvalidScheduleError(f"No song with id {target_id}.")
        return

    if target_type == "PLAYLIST":
        if db.get(Playlist, target_id) is None:
            raise InvalidScheduleError(f"No playlist with id {target_id}.")
        return

    if target_type in {"JINGLE", "ADVERTISEMENT"}:
        asset = db.get(Asset, target_id)
        if asset is None:
            raise InvalidScheduleError(f"No asset with id {target_id}.")
        actual = asset.asset_type.value if isinstance(asset.asset_type, AssetType) else asset.asset_type
        if actual != target_type:
            raise InvalidScheduleError(
                f"Asset {target_id} is {actual}, not {target_type}."
            )
        return

    raise InvalidScheduleError(f"Unsupported target_type '{target_type}'.")


def _validate_window(start_time: str, end_time: str) -> None:
    if end_time <= start_time:
        raise InvalidScheduleError("end_time must be later than start_time.")


def create_schedule(db: Session, request: ScheduleCreate) -> Schedule:
    _validate_window(request.start_time, request.end_time)
    _validate_target(db, request.target_type, request.target_id)
    schedule = ScheduleRepository(db).create({
        "name": request.name.strip(),
        "target_type": request.target_type,
        "target_id": request.target_id,
        "start_time": request.start_time,
        "end_time": request.end_time,
        "days_of_week": _canonical_days(request.days_of_week),
        "enabled": request.enabled,
    })
    db.commit()
    db.refresh(schedule)
    return schedule


def get_schedule(db: Session, schedule_id: int) -> Optional[Schedule]:
    return ScheduleRepository(db).get_by_id(schedule_id)


def list_schedules(
    db: Session,
    *,
    enabled_only: bool = False,
    day: Optional[int] = None,
) -> Sequence[Schedule]:
    return ScheduleRepository(db).list_all(
        enabled_only=enabled_only,
        day=day,
    )


def update_schedule(
    db: Session,
    schedule_id: int,
    request: ScheduleUpdate,
) -> Schedule:
    repo = ScheduleRepository(db)
    current = repo.get_by_id(schedule_id)
    if current is None:
        raise ScheduleNotFoundError(f"No schedule with id {schedule_id}.")

    values = request.model_dump(exclude_unset=True)
    if "name" in values:
        values["name"] = values["name"].strip()

    current_type = current.target_type.value if hasattr(current.target_type, "value") else current.target_type
    target_type = values.get("target_type", current_type)
    target_id = values.get("target_id", current.target_id)
    start_time = values.get("start_time", current.start_time)
    end_time = values.get("end_time", current.end_time)

    _validate_window(start_time, end_time)
    _validate_target(db, target_type, target_id)

    if "days_of_week" in values:
        values["days_of_week"] = _canonical_days(values["days_of_week"])

    values["target_type"] = target_type
    updated = repo.update(schedule_id, **values)
    db.commit()
    db.refresh(updated)
    return updated


def delete_schedule(db: Session, schedule_id: int) -> bool:
    deleted = ScheduleRepository(db).delete(schedule_id)
    if deleted:
        db.commit()
    return deleted


def enable_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = ScheduleRepository(db).set_enabled(schedule_id, True)
    db.commit()
    db.refresh(schedule)
    return schedule


def disable_schedule(db: Session, schedule_id: int) -> Schedule:
    schedule = ScheduleRepository(db).set_enabled(schedule_id, False)
    db.commit()
    db.refresh(schedule)
    return schedule
