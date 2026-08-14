from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import engine_provider, queue_manager_provider
from app.database import database as db_module
from app.database.models import Song
from app.services.queue_manager import QueueManager
from src.engine import AudioEngine

from .fakes import FakeAudioOutput, FakeDecoder


@pytest.fixture()
def fake_engine():
    """A real AudioEngine with the two hardware/codec seams faked out,
    installed as the process-wide shared engine for the duration of
    one test."""
    decoder = FakeDecoder()
    output = FakeAudioOutput()
    engine = AudioEngine(audio_output=output, decoder=decoder)
    engine_provider.reset_engine(engine)
    engine._test_decoder = decoder  # convenience handle for tests
    engine._test_output = output
    yield engine
    engine_provider.reset_engine(None)


@pytest.fixture()
def queue_manager(fake_engine):
    """A fresh QueueManager subscribed to `fake_engine`, installed as
    the process-wide shared manager for the duration of one test."""
    manager = QueueManager(fake_engine)
    queue_manager_provider.reset_queue_manager(manager)
    yield manager
    queue_manager_provider.reset_queue_manager(None)


@pytest.fixture()
def db_session(tmp_path):
    """An isolated sqlite file per test, with tables created fresh."""
    db_url = f"sqlite:///{tmp_path}/{uuid.uuid4().hex}.db"
    db_module.reset_engine(db_url)
    session = db_module.SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db_session, queue_manager):
    """A FastAPI TestClient wired to the isolated test database and the
    fake-engine-backed QueueManager."""
    from app.main import app
    from app.database.database import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_song(db_session, tmp_path):
    """Factory: create a real (empty) file on disk with a supported
    extension (so AudioDecoder.validate_file's existence/extension
    check passes for real) plus a matching `songs` row. Callers
    register the path with the test's FakeDecoder separately if they
    want it to actually "play" successfully.
    """

    counter = {"n": 0}

    def _make(*, title: str = "Test Track", enabled: bool = True, missing: bool = False, extension: str = ".mp3"):
        counter["n"] += 1
        file_path = str(tmp_path / f"track_{counter['n']}{extension}")
        if not missing:
            with open(file_path, "wb") as fh:
                fh.write(b"\x00")
        song = Song(
            file_path=file_path,
            file_name=f"track_{counter['n']}{extension}",
            title=title,
            artist="Test Artist",
            album="Test Album",
            album_artist="Test Artist",
            genre="Test",
            duration=1.0,
            file_size=1,
            format=extension.lstrip(".").upper(),
            enabled=enabled,
        )
        db_session.add(song)
        db_session.commit()
        db_session.refresh(song)
        return song

    return _make
