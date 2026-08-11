"""
app/services/library_scanner.py
=================================

Walks a folder tree, finds supported audio files, and yields per-file
scan results one at a time. This module never touches the database or
FastAPI - `library_service.py` drives it and persists the results. That
separation makes it possible to unit test folder-walking + metadata
extraction without a database, and to swap the persistence strategy
(sync now, background job later) without touching this code.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .metadata_service import TrackMetadata, UnreadableAudioFileError, extract_metadata

logger = logging.getLogger(__name__)

# Formats supported today. Adding FLAC/AAC/M4A/OGG later is adding an
# extension here plus a loader in metadata_service._LOADERS - nothing
# else in the scanner needs to change.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav"})


class InvalidFolderError(Exception):
    """Raised when the folder path given to the scanner is not usable."""


@dataclass
class ScanResult:
    """Outcome of attempting to process a single discovered file."""

    file_path: str
    status: str  # "added" | "updated" | "error"
    metadata: Optional[TrackMetadata] = None
    error: Optional[str] = None


def validate_folder(folder_path: str) -> Path:
    """
    Validate that `folder_path` is a real, readable directory.

    Raises:
        InvalidFolderError: path missing, not a directory, or unreadable.
    """
    if not folder_path or not folder_path.strip():
        raise InvalidFolderError("Folder path must not be empty.")

    path = Path(folder_path).expanduser()

    if not path.exists():
        raise InvalidFolderError(f"Folder does not exist: {folder_path}")
    if not path.is_dir():
        raise InvalidFolderError(f"Path is not a folder: {folder_path}")
    if not os.access(path, os.R_OK):
        raise InvalidFolderError(f"Permission denied reading folder: {folder_path}")

    return path


def normalize_path(file_path: str) -> str:
    """Canonical, absolute, OS-normalized form used as the DB key."""
    return str(Path(file_path).expanduser().resolve())


def discover_audio_files(folder_path: str) -> Iterator[str]:
    """
    Recursively yield normalized absolute paths of supported audio
    files under `folder_path`, one at a time (no full-list materialized
    in memory - important for 10,000+ track libraries).

    Per-directory permission errors are logged and skipped rather than
    aborting the whole scan.
    """
    root = validate_folder(folder_path)

    for current_dir, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        dirnames.sort()
        for name in sorted(filenames):
            extension = os.path.splitext(name)[1].lower()
            if extension not in SUPPORTED_EXTENSIONS:
                continue
            full_path = os.path.join(current_dir, name)
            try:
                yield normalize_path(full_path)
            except OSError as exc:  # pragma: no cover - defensive
                logger.warning("Skipping unresolvable path '%s': %s", full_path, exc)


def _on_walk_error(error: OSError) -> None:
    logger.warning("Error walking directory during scan: %s", error)


def scan_folder(folder_path: str) -> Iterator[ScanResult]:
    """
    Discover and process every supported audio file under
    `folder_path`, yielding one `ScanResult` per file as it's processed
    (a generator, so the caller can persist incrementally instead of
    holding the whole library in memory).

    Never raises on a single bad file: unreadable/corrupt files produce
    a `ScanResult(status="error")` instead of aborting the scan.
    """
    for file_path in discover_audio_files(folder_path):
        try:
            if not os.path.isfile(file_path):
                # Deleted between discovery and processing - not an error.
                continue
            metadata = extract_metadata(file_path)
            yield ScanResult(file_path=file_path, status="added", metadata=metadata)
        except UnreadableAudioFileError as exc:
            logger.warning("Unreadable audio file '%s': %s", file_path, exc)
            yield ScanResult(file_path=file_path, status="error", error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            logger.exception("Unexpected error processing '%s'", file_path)
            yield ScanResult(file_path=file_path, status="error", error=str(exc))
