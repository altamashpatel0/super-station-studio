"""
app/database/database.py
========================

Central SQLAlchemy engine/session ownership.

V0.8 Part 2 hardening:
- create missing tables with SQLAlchemy metadata
- apply additive SQLite migrations to existing databases
- never drop/recreate the existing library database
- keep reset_engine() deterministic for tests
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .migrations.add_asset_priority_cooldown import (
    upgrade_asset_priority_cooldown,
)
from .migrations.add_playback_history import upgrade_playback_history
from .migrations.add_schedule_date_range import upgrade_schedule_date_range
from .migrations.add_promo_playlist_support import upgrade_promo_playlist_support
from . import playback_history_models  # noqa: F401

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "library.db",
)


def _make_engine(db_url: str | None = None):
    url = db_url or os.environ.get("MUSIC_LIBRARY_DB_URL")
    if not url:
        env_path = os.environ.get("MUSIC_LIBRARY_DB_PATH")
        path = env_path.strip() if env_path else DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # SQLAlchemy's SQLite URL accepts forward slashes on Windows and
        # avoids backslash escape ambiguity in generated URLs.
        path = os.path.abspath(path).replace("\\", "/")
        url = f"sqlite:///{path}"

    connect_args = {"check_same_thread": False, "timeout": 10} if url.startswith("sqlite") else {}
    new_engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(new_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=10000")
            finally:
                cursor.close()

    return new_engine


engine = _make_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def init_db() -> None:
    """
    Initialize the database without destroying existing data.

    Order is intentional:
      1. create missing tables from the current ORM model
      2. upgrade existing tables whose schema predates the current model

    Base.metadata.create_all() alone cannot add columns to an existing
    SQLite table, which is why the additive migration runs here.
    """
    Base.metadata.create_all(bind=engine)
    upgrade_asset_priority_cooldown(engine)
    upgrade_playback_history(engine)
    upgrade_schedule_date_range(engine)
    upgrade_promo_playlist_support(engine)


def reset_engine(db_url: str) -> None:
    """Repoint the module-level engine/session factory for tests."""
    global engine, SessionLocal

    old_engine = engine
    engine = _make_engine(db_url)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

    try:
        init_db()
    finally:
        if old_engine is not engine:
            old_engine.dispose()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction-safe session for non-request code."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
