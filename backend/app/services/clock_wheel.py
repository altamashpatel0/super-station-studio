from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from ..database.models import Schedule
from ..database.repositories.schedule_repository import ScheduleRepository


@dataclass(frozen=True)
class ScheduleOccurrence:
    """A resolved occurrence of a stored Schedule on one calendar date."""

    schedule_id: int
    name: str
    target_type: str
    target_id: int
    start_datetime: datetime
    end_datetime: datetime

    @classmethod
    def from_schedule(
        cls,
        schedule: Schedule,
        occurrence_date: date,
    ) -> "ScheduleOccurrence":
        start = _combine(occurrence_date, schedule.start_time)
        end = _combine(occurrence_date, schedule.end_time)
        return cls(
            schedule_id=schedule.id,
            name=schedule.name,
            target_type=(
                schedule.target_type.value
                if hasattr(schedule.target_type, "value")
                else schedule.target_type
            ),
            target_id=schedule.target_id,
            start_datetime=start,
            end_datetime=end,
        )

    def to_dict(self) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "start_datetime": self.start_datetime.isoformat(),
            "end_datetime": self.end_datetime.isoformat(),
        }


def _combine(occurrence_date: date, hhmm: str) -> datetime:
    hour = int(hhmm[:2])
    minute = int(hhmm[3:])
    return datetime.combine(
        occurrence_date,
        time(hour=hour, minute=minute),
    )


def _schedule_days(schedule: Schedule) -> set[int]:
    return set(schedule.day_list())


class ClockWheel:
    """
    Deterministic, read-only time resolver for V0.6 Part 2.

    It never starts playback and never touches AudioEngine/Queue.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repository = ScheduleRepository(db)

    def get_schedule_window(
        self,
        schedule: Schedule,
        occurrence_date: date,
    ) -> Optional[ScheduleOccurrence]:
        if not schedule.enabled:
            return None

        if occurrence_date.weekday() not in _schedule_days(schedule):
            return None

        return ScheduleOccurrence.from_schedule(
            schedule,
            occurrence_date,
        )

    def get_current_schedule(
        self,
        now: datetime,
    ) -> Optional[ScheduleOccurrence]:
        """
        Return the active schedule at `now`.

        Active interval is [start_datetime, end_datetime):
        start is included, end is excluded.

        If overlapping schedules exist, choose the one with the latest
        start time; schedule id is the deterministic final tie-breaker.
        """
        schedules: Sequence[Schedule] = self.repository.list_all(
            enabled_only=True,
            day=now.weekday(),
        )

        active: list[ScheduleOccurrence] = []

        for schedule in schedules:
            occurrence = self.get_schedule_window(
                schedule,
                now.date(),
            )
            if occurrence is None:
                continue

            if (
                occurrence.start_datetime <= now
                and now < occurrence.end_datetime
            ):
                active.append(occurrence)

        if not active:
            return None

        return max(
            active,
            key=lambda item: (
                item.start_datetime,
                item.schedule_id,
            ),
        )

    def get_next_schedule(
        self,
        now: datetime,
    ) -> Optional[ScheduleOccurrence]:
        """
        Return the earliest schedule occurrence strictly after `now`.

        Searches the next seven calendar days, including today.
        A schedule beginning exactly at `now` is not considered "next".
        """
        candidates: list[ScheduleOccurrence] = []

        for day_offset in range(0, 8):
            occurrence_date = now.date() + timedelta(days=day_offset)

            schedules = self.repository.list_all(
                enabled_only=True,
                day=occurrence_date.weekday(),
            )

            for schedule in schedules:
                occurrence = self.get_schedule_window(
                    schedule,
                    occurrence_date,
                )
                if occurrence is None:
                    continue

                if occurrence.start_datetime > now:
                    candidates.append(occurrence)

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda item: (
                item.start_datetime,
                item.schedule_id,
            ),
        )
