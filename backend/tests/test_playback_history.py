"""
V0.8 Part 3 — Reports & History tests.
"""

from __future__ import annotations

import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.database import init_db
from app.database.playback_history_models import PlaybackHistory
from app.database.migrations.add_playback_history import upgrade_playback_history
from app.services.playback_history import get_summary, list_history


def test_history_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite:///:memory:", future=True)

    assert upgrade_playback_history(engine) is True
    assert upgrade_playback_history(engine) is False
    assert "playback_history" in inspect(engine).get_table_names()


def test_history_summary_uses_real_rows():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db()

    # Use the test engine directly; create only the history table here.
    from app.database.models import Base
    Base.metadata.create_all(engine)
    upgrade_playback_history(engine)

    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    try:
        today = datetime.datetime.combine(datetime.date.today(), datetime.time(10, 0))
        db.add_all([
            PlaybackHistory(
                started_at=today,
                ended_at=today + datetime.timedelta(seconds=120),
                content_type="SONG",
                content_id=1,
                content_name="Test Song",
                file_path="C:/test-song.mp3",
                duration_seconds=120,
                status="COMPLETED",
                source="ENGINE",
            ),
            PlaybackHistory(
                started_at=today + datetime.timedelta(minutes=3),
                ended_at=today + datetime.timedelta(seconds=5),
                content_type="ADVERTISEMENT",
                content_id=2,
                content_name="Test Ad",
                file_path="C:/test-ad.mp3",
                duration_seconds=5,
                status="SKIPPED",
                source="ENGINE",
            ),
            PlaybackHistory(
                started_at=today + datetime.timedelta(minutes=4),
                content_type="JINGLE",
                content_id=3,
                content_name="Test Jingle",
                file_path="C:/test-jingle.mp3",
                duration_seconds=8,
                status="FAILED",
                source="ENGINE",
                error_message="AudioEngine playback error",
            ),
        ])
        db.commit()

        summary = get_summary(db, date=datetime.date.today())

        assert summary["total"] == 3
        assert summary["songs_played"] == 1
        assert summary["advertisements_played"] == 1
        assert summary["jingles_played"] == 1
        assert summary["completed"] == 1
        assert summary["skipped"] == 1
        assert summary["failures"] == 1
        assert summary["total_duration_seconds"] == 120
    finally:
        db.close()
        engine.dispose()


def test_history_filters():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base = __import__("app.database.models", fromlist=["Base"]).Base
    Base.metadata.create_all(engine)
    upgrade_playback_history(engine)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    try:
        now = datetime.datetime.utcnow()
        db.add_all([
            PlaybackHistory(
                started_at=now,
                content_type="SONG",
                content_name="A",
                file_path="A.mp3",
                duration_seconds=10,
                status="COMPLETED",
                source="ENGINE",
            ),
            PlaybackHistory(
                started_at=now + datetime.timedelta(seconds=1),
                content_type="ADVERTISEMENT",
                content_name="B",
                file_path="B.mp3",
                duration_seconds=5,
                status="FAILED",
                source="ENGINE",
            ),
        ])
        db.commit()

        assert len(list_history(db, content_type="SONG")) == 1
        assert len(list_history(db, status="FAILED")) == 1
    finally:
        db.close()
        engine.dispose()
