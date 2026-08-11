"""
app/services/library_service.py
=================================

Business logic layer for the Music Library. Orchestrates
`library_scanner` (filesystem) and `SongRepository` (database), and
owns the in-memory scan-job tracking used so `POST /api/library/scan`
can return immediately instead of blocking on a 10,000+ track folder
(see V0.2 spec section 13 - Performance).

Route handlers in `api/library.py` should be thin wrappers around the
functions here; they should not touch the scanner or repository
directly.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from ..database.database import session_scope
from ..database.models import ScannedFolder
from ..database.repositories.song_repository import SongRepository
from .library_scanner import InvalidFolderError, ScanResult, scan_folder, validate_folder

logger = logging.getLogger(__name__)

# Commit every N processed files instead of once per file - keeps a
# 10,000+ track scan from issuing 10,000 individual commits, while
# still surfacing incremental progress for the job-status endpoint.
_BATCH_SIZE = 100


@dataclass
class ScanJob:
    id: str
    folder_path: str
    status: str = "pending"  # pending | running | completed | failed
    processed: int = 0
    added: int = 0
    updated: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    failure_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "folder_path": self.folder_path,
            "status": self.status,
            "processed": self.processed,
            "added": self.added,
            "updated": self.updated,
            "errors": self.errors,
            "error_details": self.error_details[:20],  # cap payload size
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "failure_reason": self.failure_reason,
        }


class _JobStore:
    """Simple thread-safe in-memory job registry.

    In-memory is a deliberate V0.2 scope choice: job status only needs
    to survive the life of the backend process for a single-machine
    playout studio. If jobs need to survive a backend restart in a
    future milestone, this is the seam to swap for a DB-backed table.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()

    def create(self, folder_path: str) -> ScanJob:
        job = ScanJob(id=str(uuid.uuid4()), folder_path=folder_path)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[ScanJob]:
        with self._lock:
            return self._jobs.get(job_id)


job_store = _JobStore()


def _persist_scan_results(db: Session, folder_path: str, results) -> ScanJob:
    repo = SongRepository(db)
    job = ScanJob(id="sync", folder_path=folder_path, status="running", started_at=time.time())

    for i, result in enumerate(results, start=1):
        _apply_result(repo, job, result)
        job.processed += 1
        if i % _BATCH_SIZE == 0:
            db.commit()

    db.commit()
    job.status = "completed"
    job.finished_at = time.time()
    return job


def _apply_result(repo: SongRepository, job: ScanJob, result: ScanResult) -> None:
    if result.status == "error":
        job.errors += 1
        if result.error:
            job.error_details.append(f"{result.file_path}: {result.error}")
        return

    meta = result.metadata
    assert meta is not None
    import os as _os

    data = {
        "file_path": result.file_path,
        "file_name": _os.path.basename(result.file_path),
        "title": meta.title,
        "artist": meta.artist,
        "album": meta.album,
        "album_artist": meta.album_artist,
        "genre": meta.genre,
        "year": meta.year,
        "track_number": meta.track_number,
        "duration": meta.duration,
        "sample_rate": meta.sample_rate,
        "bitrate": meta.bitrate,
        "file_size": meta.file_size,
        "format": meta.format,
    }
    try:
        _, created = repo.upsert(data)
        if created:
            job.added += 1
        else:
            job.updated += 1
    except Exception as exc:  # pragma: no cover - defensive (DB errors)
        logger.exception("Failed to persist scan result for '%s'", result.file_path)
        job.errors += 1
        job.error_details.append(f"{result.file_path}: database error ({exc})")


def scan_folder_sync(db: Session, folder_path: str) -> ScanJob:
    """
    Scan `folder_path` and persist results *synchronously*, returning
    the completed job summary. Used directly by tests and by small/CI
    scans; the API layer instead uses `start_background_scan` for real
    usage so large folders don't block a request.
    """
    validate_folder(folder_path)  # raises InvalidFolderError early, before any work
    _remember_folder(db, folder_path)
    results = scan_folder(folder_path)
    return _persist_scan_results(db, folder_path, results)


def _remember_folder(db: Session, folder_path: str) -> None:
    from .library_scanner import normalize_path

    normalized = normalize_path(folder_path)
    existing = db.query(ScannedFolder).filter_by(folder_path=normalized).one_or_none()
    if existing is None:
        db.add(ScannedFolder(folder_path=normalized))
        db.commit()


def start_background_scan(folder_path: str) -> ScanJob:
    """
    Validate the folder up-front (so obviously-bad requests fail fast
    with a 4xx instead of a job that immediately errors out), then run
    the actual scan on a background thread and return a job handle the
    caller can poll via `get_job`.
    """
    validate_folder(folder_path)  # raises InvalidFolderError synchronously

    job = job_store.create(folder_path)

    def _run() -> None:
        job.status = "running"
        job.started_at = time.time()
        try:
            with session_scope() as db:
                _remember_folder(db, folder_path)
                repo = SongRepository(db)
                for i, result in enumerate(scan_folder(folder_path), start=1):
                    _apply_result(repo, job, result)
                    job.processed += 1
                    if i % _BATCH_SIZE == 0:
                        db.commit()
            job.status = "completed"
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Background scan of '%s' failed", folder_path)
            job.status = "failed"
            job.failure_reason = str(exc)
        finally:
            job.finished_at = time.time()

    thread = threading.Thread(target=_run, name=f"scan-{job.id[:8]}", daemon=True)
    thread.start()
    return job


def get_job(job_id: str) -> Optional[ScanJob]:
    return job_store.get(job_id)


def refresh_library(db: Session) -> dict:
    """
    Re-check every currently-enabled song's file path and soft-disable
    any that no longer exist on disk. Does not re-scan for *new* files
    (use `rescan_library` / a fresh scan for that).
    """
    import os as _os

    repo = SongRepository(db)
    missing = [path for path in repo.all_paths() if not _os.path.isfile(path)]
    disabled_count = repo.disable_by_paths(missing)
    db.commit()
    return {"checked": len(repo.all_paths()) + disabled_count, "disabled": disabled_count}


def rescan_library(db: Session) -> list[ScanJob]:
    """Re-scan every folder previously imported via `/api/library/scan`."""
    folders = db.query(ScannedFolder).all()
    jobs = []
    for folder in folders:
        try:
            jobs.append(scan_folder_sync(db, folder.folder_path))
        except InvalidFolderError as exc:
            logger.warning("Skipping vanished library folder '%s': %s", folder.folder_path, exc)
    return jobs
