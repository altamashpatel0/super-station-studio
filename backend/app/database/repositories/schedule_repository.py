from __future__ import annotations

import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Schedule


class ScheduleNotFoundError(Exception):
    """Raised when a schedule id does not exist."""


class ScheduleRepository:
    """All SQL/ORM access for the V0.6 schedules table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, schedule_id: int) -> Optional[Schedule]:
        return self.db.get(Schedule, schedule_id)

    def list_all(
        self,
        *,
        enabled_only: bool = False,
        day: Optional[int] = None,
    ) -> Sequence[Schedule]:
        stmt = select(Schedule)

        if enabled_only:
            stmt = stmt.where(Schedule.enabled.is_(True))

        if day is not None:
            stmt = stmt.where(Schedule.days_of_week.contains(f",{day},"))

        return self.db.execute(
            stmt.order_by(Schedule.start_time.asc(), Schedule.id.asc())
        ).scalars().all()

    def create(self, data: dict) -> Schedule:
        now = datetime.datetime.utcnow()
        schedule = Schedule(**data, created_at=now, updated_at=now)
        self.db.add(schedule)
        self.db.flush()
        return schedule

    def update(self, schedule_id: int, **fields) -> Schedule:
        schedule = self.get_by_id(schedule_id)
        if schedule is None:
            raise ScheduleNotFoundError(f"No schedule with id {schedule_id}.")
        for key, value in fields.items():
            setattr(schedule, key, value)
        schedule.updated_at = datetime.datetime.utcnow()
        self.db.flush()
        return schedule

    def set_enabled(self, schedule_id: int, enabled: bool) -> Schedule:
        return self.update(schedule_id, enabled=enabled)

    def delete(self, schedule_id: int) -> bool:
        schedule = self.get_by_id(schedule_id)
        if schedule is None:
            return False
        self.db.delete(schedule)
        self.db.flush()
        return True
