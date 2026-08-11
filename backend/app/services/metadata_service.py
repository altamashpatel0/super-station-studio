"""
app/services/metadata_service.py
==================================

Pure "file in, metadata dict out" component. Knows nothing about the
database or the scanner's traversal logic - it just reads tags (via
Mutagen) and technical info from a single audio file, and fills in
sensible fallbacks when tags are missing.

Kept separate from `library_scanner.py` so it's trivial to unit test
in isolation and to extend format support later (the `SUPPORTED_*`
maps below are the only thing that needs to grow for FLAC/AAC/M4A/OGG).

Tag reading (Mutagen) and audio decoding (the V0.1 `AudioDecoder`) are
deliberately two different libraries with two different tolerance
levels: Mutagen's MP3 parser does a strict frame-sync scan to compute
duration/bitrate and will raise (e.g. "can't sync to MPEG frame") on
files with malformed headers, ID3 padding, or other tag-level cruft
that PyAV/FFmpeg (used by `AudioDecoder`, and therefore by the V0.1
engine) decodes without complaint. A file that is malformed only from
Mutagen's point of view is still real, playable audio - V0.1 already
proves that by playing it - so a tag-read failure must not be treated
the same as an unreadable file. See `extract_metadata` below: Mutagen
failure triggers `_extract_via_decoder_fallback`, which reuses the
*existing* `AudioDecoder` (no duplicate decoding logic) purely to
confirm the file decodes and to recover accurate duration/sample-rate/
channel info, before falling back to the simple fixed labels the
scanner should use when tags are unreadable.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

logger = logging.getLogger(__name__)

# Extension -> Mutagen loader. Adding a new supported format is a single
# extra entry here (e.g. ".flac": FLAC) plus the matching entry in
# `library_scanner.SUPPORTED_EXTENSIONS`.
_LOADERS = {
    ".mp3": MP3,
    ".wav": WAVE,
}


class UnreadableAudioFileError(Exception):
    """
    Raised only when a file matching a supported extension cannot be
    read *at all* - neither Mutagen (tags) nor the V0.1 `AudioDecoder`
    (actual audio data) can make sense of it. This is reserved for
    genuinely corrupt/truncated/non-audio files; a tag-parsing failure
    alone is recovered via `_extract_via_decoder_fallback` and does not
    raise this.
    """


@dataclass
class TrackMetadata:
    title: str
    artist: str
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    year: Optional[int] = None
    track_number: Optional[int] = None
    duration: float = 0.0
    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None
    file_size: int = 0
    format: str = field(default="")
    # "tags" (normal path) or "decoder_fallback" (Mutagen couldn't read
    # tags, but the file was confirmed playable and technical info was
    # recovered via the V0.1 decoder). Surfaced mainly for logging/
    # diagnostics; not persisted to the songs table.
    metadata_source: str = "tags"


# "Artist - Title" or "Artist_-_Title" style filenames, the common case
# for downloaded/ripped tracks.
_FILENAME_ARTIST_TITLE_RE = re.compile(r"^\s*(?P<artist>.+?)\s*-\s*(?P<title>.+?)\s*$")


def _fallback_title_artist(file_name_no_ext: str) -> tuple[str, str]:
    """
    Derive (title, artist) from a filename when tags are missing.

    "Arijit Singh - Tum Hi Ho" -> ("Tum Hi Ho", "Arijit Singh")
    "Song 3"                   -> ("Song 3", "Unknown Artist")
    """
    cleaned = file_name_no_ext.replace("_", " ").strip()
    match = _FILENAME_ARTIST_TITLE_RE.match(cleaned)
    if match:
        artist = match.group("artist").strip()
        title = match.group("title").strip()
        if artist and title:
            return title, artist
    return cleaned or "Unknown Title", "Unknown Artist"


def _first(values) -> Optional[str]:
    if not values:
        return None
    value = values[0] if isinstance(values, (list, tuple)) else values
    text = str(value).strip()
    return text or None


def _parse_year(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    match = re.search(r"(\d{4})", raw)
    return int(match.group(1)) if match else None


def _parse_track_number(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    # Tags often store "3/12" (track 3 of 12).
    match = re.match(r"\s*(\d+)", raw)
    return int(match.group(1)) if match else None


def extract_metadata(file_path: str) -> TrackMetadata:
    """
    Read tags + technical info from `file_path`.

    If Mutagen cannot parse the file's tags/technical info (malformed
    ID3 data, frame-sync issues, etc.), this does NOT immediately give
    up: it falls back to confirming playability and recovering
    duration/sample-rate via the existing V0.1 `AudioDecoder` (see
    `_extract_via_decoder_fallback`). Only a file that neither Mutagen
    nor the decoder can read raises `UnreadableAudioFileError`.
    """
    extension = os.path.splitext(file_path)[1].lower()
    loader = _LOADERS.get(extension, MutagenFile)

    try:
        audio = loader(file_path)
        if audio is None:
            raise UnreadableAudioFileError(f"'{file_path}' is not a recognizable audio file.")
    except Exception as exc:
        logger.warning(
            "Mutagen could not read tags for '%s' (%s). Falling back to the "
            "audio decoder to confirm playability and recover technical info.",
            file_path,
            exc,
        )
        return _extract_via_decoder_fallback(file_path, tag_read_error=exc)

    tags = audio.tags or {}
    file_name_no_ext = os.path.splitext(os.path.basename(file_path))[0]

    title = _first(tags.get("TIT2")) if hasattr(tags, "get") else None
    artist = _first(tags.get("TPE1")) if hasattr(tags, "get") else None
    album = _first(tags.get("TALB")) if hasattr(tags, "get") else None
    album_artist = _first(tags.get("TPE2")) if hasattr(tags, "get") else None
    genre = _first(tags.get("TCON")) if hasattr(tags, "get") else None
    year_raw = _first(tags.get("TDRC")) if hasattr(tags, "get") else None
    track_raw = _first(tags.get("TRCK")) if hasattr(tags, "get") else None

    # EasyID3-style / generic mutagen tags (covers WAVE/other containers
    # that don't use raw ID3 frame names, and any future format we add
    # via the mutagen.File "easy" API).
    if hasattr(tags, "get") and title is None:
        title = _first(tags.get("title"))
    if hasattr(tags, "get") and artist is None:
        artist = _first(tags.get("artist"))
    if hasattr(tags, "get") and album is None:
        album = _first(tags.get("album"))
    if hasattr(tags, "get") and album_artist is None:
        album_artist = _first(tags.get("albumartist"))
    if hasattr(tags, "get") and genre is None:
        genre = _first(tags.get("genre"))
    if hasattr(tags, "get") and year_raw is None:
        year_raw = _first(tags.get("date"))
    if hasattr(tags, "get") and track_raw is None:
        track_raw = _first(tags.get("tracknumber"))

    fallback_title, fallback_artist = _fallback_title_artist(file_name_no_ext)

    info = getattr(audio, "info", None)
    duration = float(getattr(info, "length", 0.0) or 0.0)
    sample_rate = getattr(info, "sample_rate", None)
    bitrate = getattr(info, "bitrate", None)
    if bitrate:
        bitrate = int(bitrate / 1000) if bitrate > 10000 else int(bitrate)  # normalize to kbps

    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        file_size = 0

    return TrackMetadata(
        title=title or fallback_title,
        artist=artist or fallback_artist,
        album=album or "",
        album_artist=album_artist or (artist or fallback_artist),
        genre=genre or "",
        year=_parse_year(year_raw),
        track_number=_parse_track_number(track_raw),
        duration=round(duration, 3),
        sample_rate=int(sample_rate) if sample_rate else None,
        bitrate=int(bitrate) if bitrate else None,
        file_size=file_size,
        format=extension.lstrip(".").upper(),
        metadata_source="tags",
    )


def _extract_via_decoder_fallback(file_path: str, tag_read_error: Exception) -> TrackMetadata:
    """
    Recovery path for files whose tags Mutagen cannot parse.

    Reuses the existing, unmodified V0.1 `AudioDecoder` (the same
    decoder the playback engine uses) purely to (a) confirm the file
    is genuinely playable audio and (b) recover duration/sample-rate/
    channel count from the real decoded stream - not to play or
    duplicate any playback logic.

    Raises:
        UnreadableAudioFileError: the decoder *also* could not read
            the file, meaning it is genuinely corrupt/not audio - the
            only case a file should actually be rejected.
    """
    # Imported lazily (rather than at module load) so metadata_service
    # has no hard import-time dependency on PyAV for the common path
    # where Mutagen succeeds - only files that actually need the
    # fallback pay the cost of importing/using the decoder.
    from src.decoder import AudioDecoder
    from src.models import AudioEngineError

    try:
        decoded = AudioDecoder().decode(file_path)
    except AudioEngineError as decode_exc:
        raise UnreadableAudioFileError(
            f"'{file_path}' could not be read: tag parsing failed ({tag_read_error}) "
            f"and audio decoding also failed ({decode_exc})."
        ) from decode_exc
    except Exception as decode_exc:  # pragma: no cover - defensive
        raise UnreadableAudioFileError(
            f"'{file_path}' could not be read: tag parsing failed ({tag_read_error}) "
            f"and audio decoding also failed unexpectedly ({decode_exc})."
        ) from decode_exc

    extension = os.path.splitext(file_path)[1].lower()
    file_name_no_ext = os.path.splitext(os.path.basename(file_path))[0]

    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        file_size = 0

    logger.info(
        "Recovered playable track via decoder fallback: '%s' (%.2fs, %d Hz, %d ch).",
        file_path,
        decoded.duration_seconds,
        decoded.sample_rate,
        decoded.channels,
    )

    # Deliberately literal fallbacks here (full filename as title, no
    # "Artist - Title" splitting) - unlike the "tags simply absent"
    # path above, we have zero trustworthy metadata for this file, so
    # we don't try to be clever about parsing the filename.
    return TrackMetadata(
        title=file_name_no_ext or "Unknown Title",
        artist="Unknown Artist",
        album="Unknown Album",
        album_artist="Unknown Artist",
        genre="Unknown",
        year=None,
        track_number=None,
        duration=round(decoded.duration_seconds, 3),
        sample_rate=int(decoded.sample_rate) if decoded.sample_rate else None,
        bitrate=None,  # not available from the decoder's PCM output
        file_size=file_size,
        format=extension.lstrip(".").upper(),
        metadata_source="decoder_fallback",
    )
