from __future__ import annotations

import datetime as dt

from app.database.models import PlaylistTrack, QueueItemStatus, Song
from app.database.repositories.playlist_repository import PlaylistRepository
from app.services.queue_manager import QueueManager
from app.services.scheduler_runtime import SchedulerRuntime
from app.services.scheduler_selection import SelectionResult
from src.models import TrackEndReason


def _song(db, path, title):
    s = Song(file_path=str(path), file_name=f"{title}.mp3", title=title, artist="A", album="B", album_artist="A", genre="Test", duration=10.0, file_size=1, format="MP3", enabled=True)
    db.add(s); db.commit(); db.refresh(s); return s


def test_scheduled_playlist_materializes_entire_playlist_and_advances(db_session, fake_engine, make_song):
    a = make_song(title="A")
    b = make_song(title="B")
    c = make_song(title="C")
    for s in (a, b, c):
        fake_engine._test_decoder.register(s.file_path)

    repo = PlaylistRepository(db_session)
    pl = repo.create("Scheduled")
    repo.add_track(pl.id, a.id)
    repo.add_track(pl.id, b.id)
    repo.add_track(pl.id, c.id)
    db_session.commit()

    manager = QueueManager(fake_engine)
    result = manager.start_scheduled_playlist(db_session, pl.id)
    assert result["file_path"] == a.file_path

    queue = list(__import__("app.database.repositories.queue_repository", fromlist=["QueueRepository"]).QueueRepository(db_session).list_all())
    assert [x.song_id for x in queue] == [a.id, b.id, c.id]
    assert queue[0].status == QueueItemStatus.PLAYING
    assert queue[1].status == QueueItemStatus.QUEUED

    fake_engine._test_output.simulate_completion()
    queue = list(__import__("app.database.repositories.queue_repository", fromlist=["QueueRepository"]).QueueRepository(db_session).list_all())
    assert queue[0].status == QueueItemStatus.PLAYED
    assert queue[1].status == QueueItemStatus.PLAYING


def test_scheduler_runtime_routes_playlist_to_queue_manager(monkeypatch):
    from unittest.mock import MagicMock
    from contextlib import contextmanager

    engine = MagicMock()
    asset = MagicMock()
    qm = MagicMock()
    db = MagicMock()
    runtime = SchedulerRuntime(engine, asset, queue_manager=qm, session_factory=lambda: _ctx(db))
    selection = SelectionResult(1, "PLAYLIST", 9, 10, "A", "/tmp/a.mp3", 10.0, "PLAYLIST_TRACK")
    occurrence = MagicMock(schedule_id=1, start_datetime=dt.datetime(2026,8,27,9,0))
    monkeypatch.setattr("app.services.scheduler_runtime.ClockWheel.get_current_schedule", lambda self, now: occurrence)
    monkeypatch.setattr("app.services.scheduler_runtime.select_for_current_schedule", lambda db, now: selection)
    runtime.tick(dt.datetime(2026,8,27,9,30))
    qm.start_scheduled_playlist.assert_called_once_with(db, 9)
    engine.load_track.assert_not_called()


def _ctx(db):
    @contextmanager
    def ctx():
        yield db
    return ctx()
