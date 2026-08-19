"""
app/database/migrations/add_asset_priority_cooldown.py
======================================================

V0.8 Part 2 database compatibility migration.

Problem fixed:
Older V0.5/V0.6 databases can already contain an `assets` table created
before `priority` and `cooldown_seconds` were introduced. SQLAlchemy's
create_all() does NOT alter existing tables, so the application can fail
with:

    sqlite3.OperationalError: no such column: assets.priority

This migration is:
- additive only
- idempotent
- data preserving
- safe on fresh databases
- safe to run on every application startup
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_TABLE = "assets"

_NEW_COLUMNS = (
    ("priority", "INTEGER NOT NULL DEFAULT 0"),
    ("cooldown_seconds", "INTEGER NOT NULL DEFAULT 0"),
)

_PRIORITY_INDEX = "ix_assets_priority"


def upgrade_asset_priority_cooldown(engine: Engine) -> list[str]:
    """
    Add missing asset playback metadata columns to an existing database.

    Returns a list containing columns that were actually added.

    The function never drops, recreates, or rewrites existing rows.
    """
    inspector = inspect(engine)

    if _TABLE not in inspector.get_table_names():
        # create_all() is responsible for a brand-new assets table.
        return []

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    added: list[str] = []

    with engine.begin() as connection:
        for column_name, ddl in _NEW_COLUMNS:
            if column_name in existing:
                continue

            connection.execute(
                text(
                    f"ALTER TABLE {_TABLE} "
                    f"ADD COLUMN {column_name} {ddl}"
                )
            )
            added.append(column_name)

        # The ORM model declares an index on priority. Existing databases
        # created before that index should receive it as well.
        indexes = {
            index.get("name")
            for index in inspect(connection).get_indexes(_TABLE)
        }

        if "priority" in existing or "priority" in {name for name, _ in _NEW_COLUMNS}:
            if _PRIORITY_INDEX not in indexes:
                connection.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS "
                        f"{_PRIORITY_INDEX} ON {_TABLE} (priority)"
                    )
                )

    return added


__all__ = ["upgrade_asset_priority_cooldown"]
