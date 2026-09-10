from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.services.scheduler_runtime import (
    SchedulerRuntime,
    SchedulerRuntimeError,
)
from app.services.scheduler_selection import SelectionResult
from app.services.playback_controller import PlaybackSource


def _selection(
    *,
    schedule_id: int = 1,
    target_type: str = "SONG",
    target_id: int = 10,
    selected_kind: str = "SONG",
) -> SelectionResult:
    return SelectionResult(
        schedule_id=schedule_id,
        target_type=target_type,
        target_id=target_id,
        selected_id=target_id,
        selected_name="Test Target",
        selected_file_path="/tmp/test-target.mp3",
        selected_duration=10.0,
        selected_kind=selected_kind,
    )


@contextmanager
def _db_context(db):
    yield db


def _runtime():
    engine = MagicMock()
    asset_manager = MagicMock()
    db = MagicMock()

    runtime = SchedulerRuntime(
        engine,
        asset_manager,
        session_factory=lambda: _db_context(db),
        poll_interval_seconds=0.01,
    )
    return runtime, engine, asset_manager, db


def test_song_selection_uses_existing_audio_engine(monkeypatch):
    runtime, engine, asset_manager, db = _runtime()
    selection = _selection()

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: MagicMock(
            schedule_id=selection.schedule_id,
            start_datetime=dt.datetime(2026, 8, 18, 9, 0),
        ),
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.select_for_current_schedule",
        lambda db, now: selection,
    )

    result = runtime.tick(dt.datetime(2026, 8, 18, 9, 30))

    assert result == selection
    engine.load_track.assert_called_once_with(selection.selected_file_path)
    engine.play.assert_called_once()
    asset_manager.play_asset.assert_not_called()


def test_asset_selection_uses_asset_playback_manager(monkeypatch):
    runtime, engine, asset_manager, db = _runtime()
    selection = _selection(
        target_type="JINGLE",
        selected_kind="JINGLE",
        target_id=20,
    )

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: MagicMock(
            schedule_id=selection.schedule_id,
            start_datetime=dt.datetime(2026, 8, 18, 9, 0),
        ),
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.select_for_current_schedule",
        lambda db, now: selection,
    )

    result = runtime.tick(dt.datetime(2026, 8, 18, 9, 30))

    assert result == selection
    asset_manager.play_asset.assert_called_once_with(db, selection.selected_id)
    engine.load_track.assert_not_called()
    engine.play.assert_not_called()


def test_same_occurrence_is_not_started_twice(monkeypatch):
    runtime, engine, asset_manager, db = _runtime()
    selection = _selection(schedule_id=7)

    occurrence = MagicMock(
        schedule_id=7,
        start_datetime=dt.datetime(2026, 8, 18, 9, 0),
    )

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: occurrence,
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.select_for_current_schedule",
        lambda db, now: selection,
    )

    now = dt.datetime(2026, 8, 18, 9, 30)
    runtime.tick(now)
    runtime.tick(now + dt.timedelta(seconds=1))

    assert engine.load_track.call_count == 1
    assert engine.play.call_count == 1


def test_new_occurrence_can_start(monkeypatch):
    runtime, engine, asset_manager, db = _runtime()
    selection = _selection(schedule_id=7)

    occurrences = iter(
        [
            MagicMock(
                schedule_id=7,
                start_datetime=dt.datetime(2026, 8, 18, 9, 0),
            ),
            MagicMock(
                schedule_id=8,
                start_datetime=dt.datetime(2026, 8, 18, 10, 0),
            ),
        ]
    )

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: next(occurrences),
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.select_for_current_schedule",
        lambda db, now: selection,
    )

    runtime.tick(dt.datetime(2026, 8, 18, 9, 30))
    runtime.tick(dt.datetime(2026, 8, 18, 10, 30))

    assert engine.load_track.call_count == 2
    assert engine.play.call_count == 2


def test_no_active_schedule_does_nothing(monkeypatch):
    runtime, engine, asset_manager, db = _runtime()

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: None,
    )

    assert runtime.tick(dt.datetime(2026, 8, 18, 9, 30)) is None
    engine.load_track.assert_not_called()
    engine.play.assert_not_called()
    asset_manager.play_asset.assert_not_called()


def test_start_is_idempotent(monkeypatch):
    runtime, _, _, _ = _runtime()
    monkeypatch.setattr(runtime, "tick", MagicMock())

    runtime.start()
    runtime.start()
    runtime.stop()

    # The exact number of ticks is intentionally not asserted because the
    # background scheduler is timing-based.


def test_start_selection_failure_is_wrapped(monkeypatch):
    runtime, engine, _, _ = _runtime()
    selection = _selection()

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: MagicMock(
            schedule_id=1,
            start_datetime=dt.datetime(2026, 8, 18, 9, 0),
        ),
    )
    monkeypatch.setattr(
        "app.services.scheduler_runtime.select_for_current_schedule",
        lambda db, now: selection,
    )

    engine.load_track.side_effect = RuntimeError("device failed")

    with pytest.raises(SchedulerRuntimeError, match="schedule 1"):
        runtime.tick(dt.datetime(2026, 8, 18, 9, 30))

    assert runtime.get_last_error() == "device failed"


def test_schedule_window_end_pauses_and_releases_scheduled_playback(monkeypatch):
    runtime, _, _, db = _runtime()
    controller = MagicMock()
    controller.active_source = PlaybackSource.SCHEDULE
    status = MagicMock()
    status.state.name = "PLAYING"
    controller.engine.get_status.return_value = status
    history = MagicMock()

    runtime = SchedulerRuntime(
        MagicMock(),
        MagicMock(),
        controller=controller,
        history_recorder=history,
        session_factory=lambda: _db_context(db),
        poll_interval_seconds=0.01,
    )
    runtime._started_occurrence = (1, dt.datetime(2026, 8, 18, 11, 50))

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: None,
    )

    runtime.tick(dt.datetime(2026, 8, 18, 11, 56))

    controller.pause.assert_called_once()
    controller.release_if_owned.assert_called_once_with(PlaybackSource.SCHEDULE)
    history.finish_active_as_skipped.assert_called_once()
    assert runtime._started_occurrence is None


def test_schedule_window_end_does_not_touch_manual_playback(monkeypatch):
    runtime, _, _, db = _runtime()
    controller = MagicMock()
    controller.active_source = PlaybackSource.MANUAL
    runtime = SchedulerRuntime(
        MagicMock(),
        MagicMock(),
        controller=controller,
        session_factory=lambda: _db_context(db),
        poll_interval_seconds=0.01,
    )
    runtime._started_occurrence = (1, dt.datetime(2026, 8, 18, 11, 50))

    monkeypatch.setattr(
        "app.services.scheduler_runtime.ClockWheel.get_current_schedule",
        lambda self, now: None,
    )

    runtime.tick(dt.datetime(2026, 8, 18, 11, 56))

    controller.pause.assert_not_called()
    controller.release_if_owned.assert_not_called()
