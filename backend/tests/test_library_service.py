"""tests/test_library_service.py — scan/refresh/rescan orchestration."""

from __future__ import annotations

import time

from app.database.repositories.song_repository import SongRepository
from app.services import library_service
from app.services.library_scanner import InvalidFolderError
import pytest


def test_scan_folder_sync_persists_all_tracks(db_session, music_folder):
    job = library_service.scan_folder_sync(db_session, str(music_folder))

    assert job.status == "completed"
    assert job.added == 3
    assert job.updated == 0
    assert job.errors == 0

    songs = SongRepository(db_session).list_all()
    assert len(songs) == 3


def test_scan_folder_sync_rejects_invalid_folder(db_session, tmp_path):
    with pytest.raises(InvalidFolderError):
        library_service.scan_folder_sync(db_session, str(tmp_path / "nope"))


def test_rescanning_same_folder_updates_not_duplicates(db_session, music_folder):
    library_service.scan_folder_sync(db_session, str(music_folder))
    job2 = library_service.scan_folder_sync(db_session, str(music_folder))

    assert job2.added == 0
    assert job2.updated == 3
    assert len(SongRepository(db_session).list_all()) == 3


def test_scan_records_errors_without_failing_whole_scan(db_session, music_folder):
    (music_folder / "corrupt.mp3").write_bytes(b"not real audio data")

    job = library_service.scan_folder_sync(db_session, str(music_folder))

    assert job.added == 3
    assert job.errors == 1
    assert len(job.error_details) == 1


def test_refresh_disables_missing_files(db_session, music_folder):
    library_service.scan_folder_sync(db_session, str(music_folder))
    songs = SongRepository(db_session).list_all()
    assert all(s.enabled for s in songs)

    target = next(s for s in songs if s.file_name == "Kesariya.mp3")
    import os
    os.remove(target.file_path)

    result = library_service.refresh_library(db_session)

    assert result["disabled"] == 1
    refreshed = SongRepository(db_session).get_by_id(target.id)
    assert refreshed.enabled is False
    # The row still exists (soft handling) - play history/id preserved.
    assert refreshed.id == target.id


def test_refresh_does_not_touch_present_files(db_session, music_folder):
    library_service.scan_folder_sync(db_session, str(music_folder))
    result = library_service.refresh_library(db_session)
    assert result["disabled"] == 0
    assert all(s.enabled for s in SongRepository(db_session).list_all())


def test_rescan_library_reprocesses_known_folders(db_session, music_folder):
    library_service.scan_folder_sync(db_session, str(music_folder))

    # Add a new track after the initial scan, then rescan without
    # re-supplying the folder path.
    from tests.conftest import _make_silent_wav
    _make_silent_wav(music_folder / "New Song.wav")

    jobs = library_service.rescan_library(db_session)

    assert len(jobs) == 1
    assert jobs[0].added == 1  # the new file
    assert jobs[0].updated == 3  # the three pre-existing files
    assert len(SongRepository(db_session).list_all()) == 4


def test_background_scan_completes_and_is_pollable(db_session, music_folder):
    job = library_service.start_background_scan(str(music_folder))
    assert job.status in ("pending", "running")

    deadline = time.time() + 10
    while time.time() < deadline:
        fetched = library_service.get_job(job.id)
        if fetched.status == "completed":
            break
        time.sleep(0.05)

    fetched = library_service.get_job(job.id)
    assert fetched.status == "completed"
    assert fetched.added == 3


def test_background_scan_rejects_invalid_folder_synchronously(tmp_path):
    with pytest.raises(InvalidFolderError):
        library_service.start_background_scan(str(tmp_path / "missing"))


def test_get_job_unknown_id_returns_none():
    assert library_service.get_job("not-a-real-job-id") is None
