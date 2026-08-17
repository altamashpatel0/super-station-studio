"""
app/database/migrations/add_asset_priority_cooldown.py
=========================================================

V0.5 Part 2 schema update: adds `priority` and `cooldown_seconds` to
an *existing* `assets` table in place.

Why a hand-rolled migration instead of `Base.metadata.create_all()`:
`create_all` only creates tables that don't exist yet - it never
alters an existing table's columns, so on any database that already
has V0.5 Part 1's `assets` table (with real imported jingles/ads in
it), the new columns would simply never appear. This module closes
that gap without dropping or recreating anything.

Safety properties:
  - Idempotent: inspects `assets`'s current columns first and only
    issues an `ALTER TABLE ... ADD COLUMN` for a column that's
    actually missing. Safe to call on every application startup,
    including against a fresh V0.5 Part 2 database that already has
    both columns (from `Base.metadata.create_all`) - it's then a
    no-op.
  - Additive only: only ever adds columns to `assets`. Never drops,
    renames, or recreates any table, and never touches `songs`,
    `scanned_folders`, `playlists`, `playlist_tracks`, or
    `queue_items`.
  - Data-preserving: `ALTER TABLE ADD COLUMN ... DEFAULT ...` backfills
    the default for every existing row in the same statement (SQLite
    semantics) - no existing asset row, and no other table's data, is
    touched.
  - No-op if `assets` doesn't exist yet at all (e.g. a brand-new
    database): in that case `Base.metadata.create_all()` will create
    it with the new columns already present, so there's nothing for
    this migration to do.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

_TABLE = "assets"

# (column_name, DDL fragment). Order matters only for readability.
_NEW_COLUMNS = [
    ("priority", "INTEGER NOT NULL DEFAULT 0"),
    ("cooldown_seconds", "INTEGER NOT NULL DEFAULT 0"),
]


def upgrade_asset_priority_cooldown(engine: Engine) -> list[str]:
    """Add any missing `priority`/`cooldown_seconds` columns to an
    existing `assets` table. Returns the list of column names that
    were actually added (empty list if nothing needed to change).

    Call this once at application startup, after
    `Base.metadata.create_all(bind=engine)` (so a brand-new database
    gets a `assets` table with both columns already, and this becomes
    a no-op), and before the app starts serving requests.
    """
    inspector = inspect(engine)

    if _TABLE not in inspector.get_table_names():
        # Nothing to migrate - `create_all` will create the table with
        # both columns already present (see module docstring).
        return []

    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    added: list[str] = []

    with engine.begin() as conn:
        for column_name, ddl in _NEW_COLUMNS:
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {column_name} {ddl}"))
            added.append(column_name)

    return added
