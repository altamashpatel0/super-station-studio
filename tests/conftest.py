"""
tests/conftest.py
===================

Shared pytest fixtures for the V0.2 Music Library test suite.

Audio fixtures are synthesized on the fly with ffmpeg (silent/tone
WAV and MP3 files a few hundred milliseconds long) - nothing under
`tests/` is a real/copyrighted recording, and nothing here is
committed to the repo; fixtures live in pytest's `tmp_path` and are
discarded after each test.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest
from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
from mutagen.mp3 import MP3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import database as db_module
from app.database.models import Base


# ----------------------------------------------------------------------
# Isolated database per test
# ----------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    """A fresh SQLite file per test, with the app's module-level engine
    repointed at it so both direct repository calls and the FastAPI
    `get_db` dependency share the same database."""
    db_path = tmp_path / "test_library.db"
    db_module.reset_engine(f"sqlite:///{db_path}")

    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the same isolated test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ----------------------------------------------------------------------
# Synthetic audio fixtures
# ----------------------------------------------------------------------


def _make_silent_wav(path: Path, duration_seconds: float = 0.5, sample_rate: int = 44100) -> Path:
    """Pure-stdlib silent WAV - no ffmpeg dependency for the WAV case."""
    n_frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * n_frames)
    return path


def _make_silent_mp3(path: Path, duration_seconds: float = 0.5) -> Path:
    """A real, tiny, valid MP3 generated with ffmpeg (silent tone)."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_seconds),
            "-codec:a", "libmp3lame", "-b:a", "64k",
            str(path),
        ],
        check=True,
    )
    return path


def _tag_mp3(path: Path, *, title=None, artist=None, album=None, album_artist=None,
             genre=None, year=None, track=None) -> None:
    audio = MP3(str(path))
    if audio.tags is None:
        audio.add_tags()
    if title is not None:
        audio.tags.add(TIT2(encoding=3, text=title))
    if artist is not None:
        audio.tags.add(TPE1(encoding=3, text=artist))
    if album is not None:
        audio.tags.add(TALB(encoding=3, text=album))
    if album_artist is not None:
        audio.tags.add(TPE2(encoding=3, text=album_artist))
    if genre is not None:
        audio.tags.add(TCON(encoding=3, text=genre))
    if year is not None:
        audio.tags.add(TDRC(encoding=3, text=str(year)))
    if track is not None:
        audio.tags.add(TRCK(encoding=3, text=str(track)))
    audio.save()


@pytest.fixture()
def make_mp3(tmp_path):
    """Factory fixture: make_mp3(filename, **tags) -> Path to a tiny, valid, tagged MP3."""

    def _factory(filename: str = "track.mp3", *, subdir: str = "", **tags) -> Path:
        folder = tmp_path / subdir if subdir else tmp_path
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        _make_silent_mp3(path)
        if tags:
            _tag_mp3(path, **tags)
        return path

    return _factory


@pytest.fixture()
def make_wav(tmp_path):
    """Factory fixture: make_wav(filename) -> Path to a tiny, valid WAV (no tags)."""

    def _factory(filename: str = "track.wav", *, subdir: str = "", duration_seconds: float = 0.5) -> Path:
        folder = tmp_path / subdir if subdir else tmp_path
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        _make_silent_wav(path, duration_seconds=duration_seconds)
        return path

    return _factory


@pytest.fixture()
def music_folder(tmp_path, make_mp3, make_wav):
    """
    A small, realistic library folder tree used by scanner/service/API
    tests:

        music/
          Arijit Singh - Tum Hi Ho.mp3     (tagged)
          Album/
            Kesariya.mp3                    (tagged, different artist)
            Song 3.wav                      (untagged -> filename fallback)
          not_audio.txt
    """
    root = tmp_path / "music"
    root.mkdir()

    make_mp3(
        "Arijit Singh - Tum Hi Ho.mp3",
        subdir="music",
        title="Tum Hi Ho",
        artist="Arijit Singh",
        album="Aashiqui 2",
        genre="Bollywood",
        year=2013,
        track=1,
    )
    make_mp3(
        "Kesariya.mp3",
        subdir="music/Album",
        title="Kesariya",
        artist="Arijit Singh",
        album="Brahmastra",
        genre="Bollywood",
        year=2022,
        track=2,
    )
    make_wav("Song 3.wav", subdir="music/Album")

    (root / "not_audio.txt").write_text("not an audio file")

    return root
