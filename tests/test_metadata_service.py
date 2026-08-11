"""tests/test_metadata_service.py — Mutagen-backed metadata extraction."""

from __future__ import annotations

import pytest

from app.services.metadata_service import UnreadableAudioFileError, extract_metadata


def test_extracts_full_tags_from_mp3(make_mp3):
    path = make_mp3(
        "song.mp3",
        title="Tum Hi Ho",
        artist="Arijit Singh",
        album="Aashiqui 2",
        album_artist="Various Artists",
        genre="Bollywood",
        year=2013,
        track=1,
    )
    meta = extract_metadata(str(path))

    assert meta.title == "Tum Hi Ho"
    assert meta.artist == "Arijit Singh"
    assert meta.album == "Aashiqui 2"
    assert meta.album_artist == "Various Artists"
    assert meta.genre == "Bollywood"
    assert meta.year == 2013
    assert meta.track_number == 1
    assert meta.format == "MP3"
    assert meta.duration > 0
    assert meta.file_size > 0


def test_missing_metadata_falls_back_to_filename(make_mp3):
    # "Arijit Singh - Tum Hi Ho.mp3" with NO tags at all.
    path = make_mp3("Arijit Singh - Tum Hi Ho.mp3")
    meta = extract_metadata(str(path))

    assert meta.title == "Tum Hi Ho"
    assert meta.artist == "Arijit Singh"


def test_missing_metadata_no_artist_pattern_uses_unknown_artist(make_mp3):
    path = make_mp3("Song 3.mp3")
    meta = extract_metadata(str(path))

    assert meta.title == "Song 3"
    assert meta.artist == "Unknown Artist"


def test_existing_metadata_is_not_overridden_by_filename(make_mp3):
    # Filename looks like "Artist - Title" but tags say otherwise -
    # tags must win; scanner should not make aggressive assumptions.
    path = make_mp3(
        "Wrong Artist - Wrong Title.mp3",
        title="Real Title",
        artist="Real Artist",
    )
    meta = extract_metadata(str(path))

    assert meta.title == "Real Title"
    assert meta.artist == "Real Artist"


def test_wav_metadata_extraction(make_wav):
    path = make_wav("plain_track.wav", duration_seconds=0.75)
    meta = extract_metadata(str(path))

    assert meta.format == "WAV"
    assert meta.duration == pytest.approx(0.75, abs=0.05)
    # No tags in a bare WAV -> filename fallback.
    assert meta.title == "plain track"
    assert meta.artist == "Unknown Artist"


def test_corrupt_file_raises_unreadable_error(tmp_path):
    bad_file = tmp_path / "corrupt.mp3"
    bad_file.write_bytes(b"this is not an mp3 file at all, just garbage bytes")

    with pytest.raises(UnreadableAudioFileError):
        extract_metadata(str(bad_file))
