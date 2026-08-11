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


# ----------------------------------------------------------------------
# Regression: playable MP3 with metadata Mutagen cannot parse
# (reported bug - "can't sync to MPEG frame" on a file V0.1 plays fine)
# ----------------------------------------------------------------------


def test_playable_mp3_with_unreadable_tags_does_not_raise(make_mp3_with_unreadable_tags):
    """A file V0.1 can decode/play must never be rejected just because
    Mutagen's stricter tag parser chokes on it."""
    path = make_mp3_with_unreadable_tags("song.mp3")

    meta = extract_metadata(str(path))  # must NOT raise

    assert meta.metadata_source == "decoder_fallback"


def test_playable_mp3_with_unreadable_tags_uses_fallback_fields(make_mp3_with_unreadable_tags):
    path = make_mp3_with_unreadable_tags("song.mp3")
    meta = extract_metadata(str(path))

    assert meta.title == "song"  # filename without extension, no smart parsing
    assert meta.artist == "Unknown Artist"
    assert meta.album == "Unknown Album"
    assert meta.genre == "Unknown"
    assert meta.year is None
    assert meta.track_number is None


def test_playable_mp3_with_unreadable_tags_gets_real_duration(make_mp3_with_unreadable_tags):
    """Duration/sample rate must come from actually decoding the audio
    (via the existing V0.1 decoder), not be left at 0."""
    path = make_mp3_with_unreadable_tags("song.mp3")
    meta = extract_metadata(str(path))

    assert meta.duration > 0
    assert meta.sample_rate == 44100
    assert meta.format == "MP3"
    assert meta.file_size > 0


def test_playable_mp3_duration_matches_direct_decoder_output(make_mp3_with_unreadable_tags):
    """Sanity check that the fallback duration is the *actual* decoded
    duration (same value V0.1's engine would report), not a guess."""
    from src.decoder import AudioDecoder

    path = make_mp3_with_unreadable_tags("song.mp3")
    meta = extract_metadata(str(path))
    decoded = AudioDecoder().decode(str(path))

    assert meta.duration == pytest.approx(decoded.duration_seconds, abs=0.01)
