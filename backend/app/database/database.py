"""
app/database/database.py
=========================

Owns the SQLAlchemy engine/session machinery. Nothing else in the
codebase should call `create_engine` directly - route handlers and
services get sessions from `get_db` (FastAPI dependency) or
`session_scope` (plain context manager, used by the scanner service
which runs outside of a request).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

# Default location: <repo_root>/data/library.db. Overridable via env var
# so tests can point at an isolated/in-memory database.
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "library.db",
)


def _make_engine(db_url: str | None = None):
    url = db_url or os.environ.get("MUSIC_LIBRARY_DB_URL")
    if not url:
        os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
        url = f"sqlite:///{DEFAULT_DB_PATH}"

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    new_engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        # SQLite ignores FK constraints unless explicitly told to
        # enforce them per-connection. Needed as of V0.3 so invalid
        # `playlist_tracks.playlist_id` / `song_id` references are
        # rejected at the DB layer, not just by app-level checks.
        @event.listens_for(new_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return new_engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call repeatedly."""
    Base.metadata.create_all(bind=engine)


def reset_engine(db_url: str) -> None:
    """
    Repoint the module-level engine/session factory at a different
    database URL. Intended for tests (e.g. an isolated sqlite file per
    test run) - application code should not need this.
    """
    global engine, SessionLocal
    engine = _make_engine(db_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    init_db()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Plain context-manager session for use outside of FastAPI routes
    (e.g. the folder scanner), with commit-on-success / rollback-on-error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
