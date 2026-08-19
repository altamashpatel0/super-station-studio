"""
tests/test_live_station_monitor.py
==================================

V0.8 Part 1 — Live Station Monitor tests.

These tests verify the monitor is read-only and exposes only real state
from the existing engine/runtime/database seams. No fake song metadata is
invented by the implementation.
"""

from types import SimpleNamespace

from app.services.live_station_monitor import LiveStationMonitor


class FakeStatus:
    def __init__(self, **values):
        self._values = values

    def to_dict(self):
        return dict(self._values)


class FakeWatchdog:
    status = "HEALTHY"
    recovery_count = 2
    last_recovery_error = None


class FakeWorker:
    is_running = True
    last_error = None


class FakeContinuation:
    running = True


class FakeRecovery:
    last_error = None


class FakeRuntime:
    def __init__(self):
        self.engine = SimpleNamespace(
            get_status=lambda: FakeStatus(
                state="PLAYING",
                file_path=r"D:\Music\song.mp3",
                position_seconds=12.5,
                duration_seconds=180.0,
                volume=1.0,
                error_message=None,
            )
        )

    def get_last_selection(self):
        return None

    def get_last_error(self):
        return None


class FakeStation:
    is_running = True
    runtime = FakeRuntime()
    worker = FakeWorker()
    continuation = FakeContinuation()
    watchdog = FakeWatchdog()
    recovery = FakeRecovery()


def test_overall_health_is_healthy_when_runtime_components_are_healthy():
    monitor = LiveStationMonitor()

    assert (
        monitor._overall_health(
            station_running=True,
            worker_running=True,
            watchdog_status="HEALTHY",
            scheduler_error=None,
            worker_error=None,
            recovery_error=None,
            watchdog_error=None,
        )
        == "HEALTHY"
    )


def test_overall_health_is_degraded_when_worker_is_stopped():
    monitor = LiveStationMonitor()

    assert (
        monitor._overall_health(
            station_running=True,
            worker_running=False,
            watchdog_status="IDLE",
            scheduler_error=None,
            worker_error=None,
            recovery_error=None,
            watchdog_error=None,
        )
        == "DEGRADED"
    )


def test_current_metadata_is_not_invented_for_unknown_file(monkeypatch):
    monitor = LiveStationMonitor()

    class EmptySongs:
        def get_by_path(self, _):
            return None

    class EmptyAssets:
        def get_by_path(self, _):
            return None

    monkeypatch.setattr(
        "app.services.live_station_monitor.SongRepository",
        lambda _db: EmptySongs(),
    )
    monkeypatch.setattr(
        "app.services.live_station_monitor.AssetRepository",
        lambda _db: EmptyAssets(),
    )

    current = monitor._resolve_current(
        object(),
        r"D:\unknown\real-engine-file.mp3",
        {
            "state": "PLAYING",
            "file_path": r"D:\unknown\real-engine-file.mp3",
            "position_seconds": 4.0,
            "duration_seconds": 90.0,
        },
    )

    assert current["kind"] == "UNKNOWN"
    assert current["title"] is None
    assert current["artist"] is None
    assert current["duration_seconds"] == 90.0


def test_next_up_uses_only_queued_library_songs(monkeypatch):
    monitor = LiveStationMonitor()

    song_a = SimpleNamespace(
        id=1, title="A", artist="Artist A", album="Album A", duration=120.0
    )
    song_b = SimpleNamespace(
        id=2, title="B", artist="Artist B", album="Album B", duration=180.0
    )
    queued = SimpleNamespace(
        id=10, position=0, status="QUEUED", song=song_a
    )
    played = SimpleNamespace(
        id=11, position=1, status="PLAYED", song=song_b
    )

    class QueueRepo:
        def __init__(self, _db):
            pass

        def list_all(self):
            return [queued, played]

    monkeypatch.setattr(
        "app.services.live_station_monitor.QueueRepository",
        QueueRepo,
    )

    result, queued_count = monitor._next_up(object())

    assert queued_count == 1
    assert len(result) == 1
    assert result[0]["title"] == "A"
    assert result[0]["kind"] == "SONG"
