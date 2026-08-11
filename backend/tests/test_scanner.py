"""tests/test_scanner.py — folder validation, discovery, recursive scanning."""

from __future__ import annotations

import os

import pytest

from app.services.library_scanner import (
    InvalidFolderError,
    discover_audio_files,
    normalize_path,
    scan_folder,
    validate_folder,
)


def test_validate_folder_rejects_missing_path(tmp_path):
    with pytest.raises(InvalidFolderError):
        validate_folder(str(tmp_path / "does_not_exist"))


def test_validate_folder_rejects_a_file_path(tmp_path):
    a_file = tmp_path / "not_a_folder.txt"
    a_file.write_text("hi")
    with pytest.raises(InvalidFolderError):
        validate_folder(str(a_file))


def test_validate_folder_rejects_empty_string():
    with pytest.raises(InvalidFolderError):
        validate_folder("")


def test_validate_folder_accepts_real_directory(tmp_path):
    result = validate_folder(str(tmp_path))
    assert result.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits don't apply on Windows")
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses POSIX permission bits, so this can't be exercised as root",
)
def test_validate_folder_rejects_unreadable_directory(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        with pytest.raises(InvalidFolderError):
            validate_folder(str(locked))
    finally:
        locked.chmod(0o755)  # restore so tmp_path cleanup can remove it


def test_discover_finds_mp3_and_wav_only(music_folder):
    found = set(discover_audio_files(str(music_folder)))
    names = {os.path.basename(p) for p in found}

    assert names == {"Arijit Singh - Tum Hi Ho.mp3", "Kesariya.mp3", "Song 3.wav"}
    assert "not_audio.txt" not in names


def test_discover_is_recursive(music_folder):
    found = list(discover_audio_files(str(music_folder)))
    assert any("Album" in p for p in found), "expected to find files inside the nested Album/ folder"


def test_discover_yields_normalized_absolute_paths(music_folder):
    for path in discover_audio_files(str(music_folder)):
        assert os.path.isabs(path)
        assert path == normalize_path(path)


def test_scan_folder_yields_added_results_with_metadata(music_folder):
    results = list(scan_folder(str(music_folder)))
    assert len(results) == 3
    assert all(r.status == "added" for r in results)
    titles = {r.metadata.title for r in results}
    assert titles == {"Tum Hi Ho", "Kesariya", "Song 3"}


def test_scan_folder_reports_error_for_corrupt_file_without_aborting(music_folder):
    corrupt = music_folder / "corrupt.mp3"
    corrupt.write_bytes(b"garbage, not a real mp3")

    results = list(scan_folder(str(music_folder)))
    statuses = {r.status for r in results}

    assert "error" in statuses
    assert "added" in statuses  # the other 3 good files still processed
    error_result = next(r for r in results if r.status == "error")
    assert "corrupt.mp3" in error_result.file_path


def test_scan_folder_adds_playable_mp3_with_unreadable_tags(music_folder, make_mp3_with_unreadable_tags):
    """
    Regression test for the reported bug: a playable MP3 whose tags
    Mutagen can't parse ("can't sync to MPEG frame") must be ADDED to
    the scan results with fallback metadata, not skipped as an error.
    """
    make_mp3_with_unreadable_tags("song.mp3", subdir="music")

    results = list(scan_folder(str(music_folder)))
    statuses = {r.status for r in results}

    assert "error" not in statuses
    assert all(r.status == "added" for r in results)
    assert len(results) == 4  # the 3 pre-existing tracks + this one

    recovered = next(r for r in results if r.file_path.endswith("song.mp3"))
    assert recovered.metadata.title == "song"
    assert recovered.metadata.artist == "Unknown Artist"
    assert recovered.metadata.duration > 0


def test_scan_folder_skips_file_removed_during_scan(music_folder, monkeypatch):
    """A file that disappears between discovery and read should be
    silently skipped, not reported as an error."""
    import app.services.library_scanner as scanner_module

    real_discover = scanner_module.discover_audio_files

    def _discover_with_ghost(folder_path):
        for path in real_discover(folder_path):
            yield path
        yield normalize_path(str(music_folder / "ghost_track.mp3"))  # never created

    monkeypatch.setattr(scanner_module, "discover_audio_files", _discover_with_ghost)

    results = list(scan_folder(str(music_folder)))
    assert all("ghost_track" not in r.file_path for r in results)
    assert len(results) == 3  # only the 3 real files
