from __future__ import annotations

import subprocess
import uuid
import wave
from pathlib import Path

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


# ----------------------------------------------------------------------
# Synthetic audio fixtures (V0.5 - Asset Library)
#
# Real, tiny, genuinely-decodable audio files, generated on the fly
# (nothing here is a real/copyrighted recording, nothing is committed
# to the repo) - used by asset import tests, which need files that
# `src.decoder.AudioDecoder` can actually decode (unlike `make_song`'s
# one-null-byte placeholder files, which are only used for the
# playback-engine seam via `FakeDecoder`).
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
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration_seconds),
            "-codec:a", "libmp3lame", "-b:a", "64k",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture()
def make_asset_wav(tmp_path):
    """Factory fixture: make_asset_wav(filename) -> Path to a tiny,
    valid, decodable WAV. Named distinctly from any `make_wav` a
    future fixture might add elsewhere, so V0.5 asset tests never
    collide with unrelated fixtures/tests."""

    def _factory(filename: str = "asset.wav", *, duration_seconds: float = 0.5) -> Path:
        path = tmp_path / filename
        _make_silent_wav(path, duration_seconds=duration_seconds)
        return path

    return _factory


@pytest.fixture()
def make_asset_mp3(tmp_path):
    """Factory fixture: make_asset_mp3(filename) -> Path to a tiny,
    valid, decodable MP3 (untagged - only used to exercise the
    decoder, not metadata_service's tag reading)."""

    def _factory(filename: str = "asset.mp3", *, duration_seconds: float = 0.5) -> Path:
        path = tmp_path / filename
        _make_silent_mp3(path, duration_seconds=duration_seconds)
        return path

    return _factory


@pytest.fixture()
def make_audio_file(tmp_path):
    """Factory fixture: make_audio_file(filename, size_bytes=100) -> str
    path to a plain file on disk of a controllable size.

    Backward-compatible shim for tests/test_assets.py (V0.5 Part 2),
    which exercises `asset_service.import_asset`'s priority/cooldown/
    ordering/metadata-update logic against a *stub* decoder (duration
    == size_bytes / 100.0, per test_duration_is_detected_on_import).
    That stub only cares about `file_path` existing and its byte size
    - unlike `make_asset_mp3`/`make_asset_wav`, it does not need a
    real, ffmpeg-decodable audio stream. Kept distinct from those two
    fixtures (and from `make_song`'s one-null-byte placeholder) so
    each caller's actual size expectations are respected.
    """

    def _factory(filename: str = "asset.mp3", *, size_bytes: int = 100) -> str:
        path = tmp_path / filename
        # Real, decodable audio is required (AudioDecoder/PyAV rejects
        # arbitrary zero-byte content), but callers/tests key off of
        # `size_bytes` to control the *decoded duration* they expect
        # back (duration == size_bytes / 100.0), not literal on-disk
        # byte count. So instead of writing raw padding bytes, encode
        # a real silent clip of the equivalent duration.
        duration_seconds = size_bytes / 100.0
        suffix = path.suffix.lower()
        if suffix == ".wav":
            _make_silent_wav(path, duration_seconds=duration_seconds)
        else:
            _make_silent_mp3(path, duration_seconds=duration_seconds)
        return str(path)

    return _factory


# ----------------------------------------------------------------------
# Library-scan fixtures (V0.1/V0.2) - used by tests/test_api.py
# ----------------------------------------------------------------------


def _tag_mp3(
    path: Path,
    *,
    title=None,
    artist=None,
    album=None,
    album_artist=None,
    genre=None,
    year=None,
    track=None,
) -> None:
    """Write ID3 tags onto an already-encoded mp3, via mutagen."""
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = EasyID3(str(path))
    except ID3NoHeaderError:
        from mutagen.mp3 import MP3

        audio = MP3(str(path))
        audio.add_tags()
        audio.save()
        tags = EasyID3(str(path))

    if title is not None:
        tags["title"] = title
    if artist is not None:
        tags["artist"] = artist
    if album is not None:
        tags["album"] = album
    if album_artist is not None:
        tags["albumartist"] = album_artist
    if genre is not None:
        tags["genre"] = genre
    if year is not None:
        tags["date"] = str(year)
    if track is not None:
        tags["tracknumber"] = str(track)
    tags.save()


@pytest.fixture()
def make_mp3(tmp_path):
    """Factory fixture: make_mp3(filename, **tags) -> Path to a tiny,
    real, decodable, ID3-tagged MP3 usable by a full library scan."""

    def _factory(
        filename: str = "track.mp3",
        *,
        title: str = None,
        artist: str = None,
        album: str = None,
        album_artist: str = None,
        genre: str = None,
        year: int = None,
        track: int = None,
        duration_seconds: float = 0.5,
        folder: Path = None,
    ) -> Path:
        path = (folder or tmp_path) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        _make_silent_mp3(path, duration_seconds=duration_seconds)
        if any(v is not None for v in (title, artist, album, album_artist, genre, year, track)):
            _tag_mp3(
                path,
                title=title,
                artist=artist,
                album=album,
                album_artist=album_artist,
                genre=genre,
                year=year,
                track=track,
            )
        return path

    return _factory


@pytest.fixture()
def make_wav(tmp_path):
    """Factory fixture: make_wav(filename) -> Path to a tiny, real,
    decodable, untagged WAV usable by a full library scan (WAVs carry
    no metadata tags, so the scanner falls back to filename/"Unknown
    Artist"/"Unknown Genre")."""

    def _factory(
        filename: str = "track.wav",
        *,
        duration_seconds: float = 0.5,
        folder: Path = None,
    ) -> Path:
        path = (folder or tmp_path) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        _make_silent_wav(path, duration_seconds=duration_seconds)
        return path

    return _factory


@pytest.fixture()
def music_folder(tmp_path, make_mp3, make_wav):
    """A folder containing exactly the 3 tracks the test_api.py
    assertions are written against:
      - two Arijit-Singh-tagged, Bollywood-genre mp3s
      - one untagged wav (falls back to "Song 3" / "Unknown Artist")
    """
    folder = tmp_path / "music"
    folder.mkdir(exist_ok=True)
    make_mp3(
        "Arijit Singh - Tum Hi Ho.mp3",
        title="Tum Hi Ho",
        artist="Arijit Singh",
        album="Aashiqui 2",
        genre="Bollywood",
        folder=folder,
    )
    # Nested inside an "Album" subfolder (rather than at the top level)
    # so discover_audio_files' recursion is genuinely exercised, while
    # keeping the total file count at 3 (basename-based assertions in
    # test_scanner.py are unaffected by which directory a file lives in).
    make_mp3(
        "Kesariya.mp3",
        title="Kesariya",
        artist="Arijit Singh",
        album="Brahmastra",
        genre="Bollywood",
        folder=folder / "Album",
    )
    make_wav("Song 3.wav", folder=folder)
    return folder


@pytest.fixture()
def make_mp3_with_unreadable_tags(music_folder):
    """Factory fixture: make_mp3_with_unreadable_tags(filename, subdir=None)
    -> Path to a real, decodable mp3 whose ID3 tags mutagen cannot
    read (regression fixture for the "playable file with unreadable
    tags must still appear in the library, via fallback metadata"
    bug). The audio payload is genuinely decodable (ffmpeg-encoded);
    only the tag frame is corrupted.
    """

    def _factory(filename: str = "song.mp3", *, subdir: str = None, duration_seconds: float = 0.5) -> Path:
        folder = (music_folder / subdir) if subdir else music_folder
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        _make_silent_mp3(path, duration_seconds=duration_seconds)

        # Give the file valid-looking, fully-tagged ID3v2 metadata,
        # then corrupt the ID3v2 header's synchsafe size field. That
        # makes mutagen raise on *any* attempt to read the tag block
        # at all (not just one frame) - exactly the "playable file,
        # unreadable tags" case the fallback-metadata path exists for
        # - while leaving the mp3 audio stream itself, which ffmpeg
        # decodes independently of the ID3 block, fully playable.
        _tag_mp3(path, title="placeholder", artist="placeholder", album="placeholder", genre="placeholder")
        with open(path, "r+b") as fh:
            data = bytearray(fh.read())
        assert data[:3] == b"ID3", "expected an ID3v2 header at the start of the encoded mp3"
        data[6:10] = bytes([0xFF, 0xFF, 0xFF, 0xFF])  # invalid (non-synchsafe) size -> header parse fails
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        return path

    return _factory
