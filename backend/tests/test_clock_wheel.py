from __future__ import annotations

from datetime import datetime

from app.database.models import Schedule, Song
from app.services.clock_wheel import ClockWheel


def _song(db, number: int = 1):
    song = Song(
        file_path=f"/tmp/v06-clock-song-{number}.mp3",
        file_name=f"v06-clock-song-{number}.mp3",
        title=f"Clock Song {number}",
        artist="Test Artist",
        album="Test Album",
        album_artist="Test Artist",
        genre="Test",
        duration=10.0,
        file_size=1,
        format="MP3",
        enabled=True,
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


def _create_schedule(
    client,
    song_id,
    *,
    name="Schedule",
    start="09:00",
    end="10:00",
    days=None,
    enabled=True,
):
    if days is None:
        days = [0]

    return client.post(
        "/api/schedules",
        json={
            "name": name,
            "target_type": "SONG",
            "target_id": song_id,
            "start_time": start,
            "end_time": end,
            "days_of_week": days,
            "enabled": enabled,
        },
    )


def test_exact_start_is_active(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="09:00", end="10:00", days=[0]
    ).json()

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 9, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime == datetime(2026, 8, 17, 9, 0)


def test_middle_of_window_is_active(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="09:00", end="10:00", days=[0]
    ).json()

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 9, 30)
    )

    assert result is not None
    assert result.schedule_id == created["id"]


def test_exact_end_is_not_active(client, db_session):
    song = _song(db_session)
    _create_schedule(
        client, song.id, start="09:00", end="10:00", days=[0]
    )

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 10, 0)
    )

    assert result is None


def test_disabled_schedule_is_ignored(client, db_session):
    song = _song(db_session)
    _create_schedule(
        client,
        song.id,
        start="09:00",
        end="10:00",
        days=[0],
        enabled=False,
    )

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 9, 30)
    )

    assert result is None


def test_wrong_weekday_is_ignored(client, db_session):
    song = _song(db_session)
    _create_schedule(
        client, song.id, start="09:00", end="10:00", days=[1]
    )

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 9, 30)
    )

    assert result is None


def test_next_schedule_later_today(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="14:00", end="15:00", days=[0]
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 12, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime == datetime(2026, 8, 17, 14, 0)


def test_next_schedule_tomorrow(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="08:00", end="09:00", days=[1]
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 20, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime == datetime(2026, 8, 18, 8, 0)


def test_next_schedule_several_days_later(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="11:00", end="12:00", days=[4]
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 20, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime == datetime(2026, 8, 21, 11, 0)


def test_next_schedule_next_week(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="11:00", end="12:00", days=[0]
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 12, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime == datetime(2026, 8, 24, 11, 0)


def test_multiple_schedules_are_chronological(client, db_session):
    song = _song(db_session)

    later = _create_schedule(
        client,
        song.id,
        name="Later",
        start="16:00",
        end="17:00",
        days=[0],
    ).json()

    earlier = _create_schedule(
        client,
        song.id,
        name="Earlier",
        start="14:00",
        end="15:00",
        days=[0],
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 12, 0)
    )

    assert result is not None
    assert result.schedule_id == earlier["id"]
    assert result.schedule_id != later["id"]


def test_same_time_uses_schedule_id_as_deterministic_tiebreak(
    client, db_session
):
    song = _song(db_session)

    first = _create_schedule(
        client,
        song.id,
        name="First",
        start="14:00",
        end="15:00",
        days=[0],
    ).json()

    second = _create_schedule(
        client,
        song.id,
        name="Second",
        start="14:00",
        end="15:00",
        days=[0],
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 12, 0)
    )

    assert result is not None
    assert result.schedule_id == min(first["id"], second["id"])


def test_current_schedule_returns_none_before_any_window(
    client, db_session
):
    song = _song(db_session)
    _create_schedule(
        client, song.id, start="14:00", end="15:00", days=[0]
    )

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 12, 0)
    )

    assert result is None


def test_next_at_exact_start_is_strictly_future(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="14:00", end="15:00", days=[0]
    ).json()

    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 14, 0)
    )

    assert result is not None
    assert result.schedule_id == created["id"]
    assert result.start_datetime > datetime(2026, 8, 17, 14, 0)


def test_no_future_schedule_returns_none(client, db_session):
    # No schedule is created here. A recurring weekly schedule would always
    # have another future occurrence, so the old version of this test was
    # contradictory with the required next-week behavior.
    result = ClockWheel(db_session).get_next_schedule(
        datetime(2026, 8, 17, 10, 0)
    )

    assert result is None


def test_schedule_window_respects_day(client, db_session):
    song = _song(db_session)
    created = _create_schedule(
        client, song.id, start="09:00", end="10:00", days=[0]
    ).json()

    row = db_session.get(Schedule, created["id"])
    wheel = ClockWheel(db_session)

    assert wheel.get_schedule_window(
        row, datetime(2026, 8, 17).date()
    ) is not None

    assert wheel.get_schedule_window(
        row, datetime(2026, 8, 18).date()
    ) is None


def test_current_overlap_chooses_latest_start_then_id(
    client, db_session
):
    song = _song(db_session)

    first = _create_schedule(
        client,
        song.id,
        name="Wide",
        start="09:00",
        end="12:00",
        days=[0],
    ).json()

    second = _create_schedule(
        client,
        song.id,
        name="Narrow",
        start="10:00",
        end="11:00",
        days=[0],
    ).json()

    result = ClockWheel(db_session).get_current_schedule(
        datetime(2026, 8, 17, 10, 30)
    )

    assert result is not None
    assert result.schedule_id == second["id"]
    assert result.schedule_id != first["id"]
