from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.repositories.schedule_repository import ScheduleNotFoundError
from ..schemas.scheduler import ScheduleCreate, ScheduleOut, ScheduleUpdate
from ..services import scheduler_service
from ..services.clock_wheel import ClockWheel
from ..services.scheduler_selection import SelectionError, select_for_schedule
from ..services.scheduler_service import InvalidScheduleError

router = APIRouter(prefix="/api/schedules", tags=["scheduler"])


def _parse_at(value: Optional[str]) -> datetime:
    if value is None:
        return datetime.now()
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="at must be a valid ISO 8601 datetime") from exc


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(request: ScheduleCreate, db: Session = Depends(get_db)):
    try:
        return scheduler_service.create_schedule(db, request).to_dict()
    except InvalidScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[ScheduleOut])
def list_schedules(enabled_only: bool = Query(False), day: Optional[int] = Query(None, ge=0, le=6), db: Session = Depends(get_db)):
    return [x.to_dict() for x in scheduler_service.list_schedules(db, enabled_only=enabled_only, day=day)]


@router.get("/clock/current")
def current_clock(at: Optional[str] = Query(None), db: Session = Depends(get_db)):
    now = _parse_at(at)
    x = ClockWheel(db).get_current_schedule(now)
    return {"at": now.isoformat(), "schedule": x.to_dict() if x else None}


@router.get("/clock/next")
def next_clock(at: Optional[str] = Query(None), db: Session = Depends(get_db)):
    now = _parse_at(at)
    x = ClockWheel(db).get_next_schedule(now)
    return {"at": now.isoformat(), "schedule": x.to_dict() if x else None}


@router.get("/{schedule_id}/select")
def select_target(schedule_id: int, at: Optional[str] = Query(None), db: Session = Depends(get_db)):
    now = _parse_at(at)
    try:
        return {"at": now.isoformat(), "selection": select_for_schedule(db, schedule_id, now=now).to_dict()}
    except SelectionError as exc:
        status = 404 if exc.__class__.__name__ == "ScheduleSelectionNotFoundError" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    row = scheduler_service.get_schedule(db, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No schedule with id {schedule_id}.")
    return row.to_dict()


@router.put("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, request: ScheduleUpdate, db: Session = Depends(get_db)):
    try:
        return scheduler_service.update_schedule(db, schedule_id, request).to_dict()
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    if not scheduler_service.delete_schedule(db, schedule_id):
        raise HTTPException(status_code=404, detail=f"No schedule with id {schedule_id}.")


@router.post("/{schedule_id}/enable", response_model=ScheduleOut)
def enable_schedule(schedule_id: int, db: Session = Depends(get_db)):
    try:
        return scheduler_service.enable_schedule(db, schedule_id).to_dict()
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{schedule_id}/disable", response_model=ScheduleOut)
def disable_schedule(schedule_id: int, db: Session = Depends(get_db)):
    try:
        return scheduler_service.disable_schedule(db, schedule_id).to_dict()
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
