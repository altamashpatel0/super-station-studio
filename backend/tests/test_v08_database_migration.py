"""
V0.8 Part 2 — database migration regression tests.

These tests reproduce the legacy-database problem:
an existing `assets` table without priority/cooldown_seconds.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.database.database import init_db
from app.database.migrations.add_asset_priority_cooldown import (
    upgrade_asset_priority_cooldown,
)


def _legacy_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    asset_type VARCHAR NOT NULL,
                    file_path VARCHAR NOT NULL UNIQUE,
                    duration FLOAT NOT NULL DEFAULT 0.0,
                    category VARCHAR NOT NULL DEFAULT '',
                    description VARCHAR NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

    return engine


def test_legacy_assets_table_is_upgraded_without_data_loss():
    engine = _legacy_engine()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO assets
                    (name, asset_type, file_path, duration, category,
                     description, enabled, created_at, updated_at)
                VALUES
                    ('Existing Ad', 'ADVERTISEMENT', 'C:/existing-ad.mp3',
                     12.5, 'Commercial', 'Existing data', 1,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )

    added = upgrade_asset_priority_cooldown(engine)

    assert added == ["priority", "cooldown_seconds"]

    columns = {column["name"] for column in inspect(engine).get_columns("assets")}
    assert "priority" in columns
    assert "cooldown_seconds" in columns

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT name, priority, cooldown_seconds
                FROM assets
                WHERE id = 1
                """
            )
        ).mappings().one()

    assert row["name"] == "Existing Ad"
    assert row["priority"] == 0
    assert row["cooldown_seconds"] == 0


def test_migration_is_idempotent():
    """
    First call performs the migration.
    Every subsequent call must be a no-op.
    """
    engine = _legacy_engine()

    first_run = upgrade_asset_priority_cooldown(engine)
    second_run = upgrade_asset_priority_cooldown(engine)
    third_run = upgrade_asset_priority_cooldown(engine)

    assert first_run == ["priority", "cooldown_seconds"]
    assert second_run == []
    assert third_run == []

    columns = {column["name"] for column in inspect(engine).get_columns("assets")}
    assert {"priority", "cooldown_seconds"}.issubset(columns)


def test_current_model_initialization_still_works():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )

    from app.database import database

    old_engine = database.engine
    old_session = database.SessionLocal

    try:
        database.engine = engine
        database.SessionLocal = database.sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            future=True,
        )

        init_db()

        columns = {
            column["name"]
            for column in inspect(engine).get_columns("assets")
        }
        assert "priority" in columns
        assert "cooldown_seconds" in columns

    finally:
        database.engine = old_engine
        database.SessionLocal = old_session
        engine.dispose()
