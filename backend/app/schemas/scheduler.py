from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


TARGET_TYPES = {"SONG", "JINGLE", "ADVERTISEMENT", "PLAYLIST"}


def _validate_hhmm(value: str) -> str:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("time must use HH:MM format")
    try:
        hour = int(value[:2])
        minute = int(value[3:])
    except ValueError as exc:
        raise ValueError("time must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must use HH:MM format")
    return value


def _validate_days(value: list[int]) -> list[int]:
    if not value:
        raise ValueError("days_of_week must contain at least one day")
    if any(day < 0 or day > 6 for day in value):
        raise ValueError("days_of_week values must be between 0 and 6")
    if len(set(value)) != len(value):
        raise ValueError("days_of_week must not contain duplicates")
    return sorted(value)


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_type: str
    target_id: int = Field(..., gt=0)
    start_time: str
    end_time: str
    days_of_week: list[int] = Field(..., min_length=1, max_length=7)
    enabled: bool = True

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: str) -> str:
        value = value.upper()
        if value not in TARGET_TYPES:
            raise ValueError(
                "target_type must be one of SONG, JINGLE, ADVERTISEMENT, PLAYLIST"
            )
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        return _validate_hhmm(value)

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, value: list[int]) -> list[int]:
        return _validate_days(value)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        return self


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_type: Optional[str] = None
    target_id: Optional[int] = Field(None, gt=0)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[list[int]] = Field(None, min_length=1, max_length=7)
    enabled: Optional[bool] = None

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.upper()
        if value not in TARGET_TYPES:
            raise ValueError(
                "target_type must be one of SONG, JINGLE, ADVERTISEMENT, PLAYLIST"
            )
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validate_hhmm(value)

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        return None if value is None else _validate_days(value)

    @model_validator(mode="after")
    def validate_window_if_complete(self):
        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be later than start_time")
        return self


class ScheduleOut(BaseModel):
    id: int
    name: str
    target_type: str
    target_id: int
    start_time: str
    end_time: str
    days_of_week: list[int]
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
