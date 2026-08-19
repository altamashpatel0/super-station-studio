"""
V0.8 Part 3 migration: playback_history.

Additive and idempotent. Existing library/assets/queue data is untouched.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade_playback_history(engine: Engine) -> bool:
    inspector = inspect(engine)
    if "playback_history" in inspector.get_table_names():
        return False

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE playback_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at DATETIME NOT NULL,
                    ended_at DATETIME NULL,
                    content_type VARCHAR(32) NOT NULL,
                    content_id INTEGER NULL,
                    content_name VARCHAR(512) NOT NULL,
                    file_path TEXT NOT NULL,
                    duration_seconds FLOAT NOT NULL DEFAULT 0.0,
                    status VARCHAR(32) NOT NULL,
                    source VARCHAR(32) NOT NULL DEFAULT 'ENGINE',
                    error_message TEXT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_started_at "
                "ON playback_history (started_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_content_type "
                "ON playback_history (content_type)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_content_id "
                "ON playback_history (content_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_status "
                "ON playback_history (status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_started_type "
                "ON playback_history (started_at, content_type)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_playback_history_started_status "
                "ON playback_history (started_at, status)"
            )
        )
    return True
