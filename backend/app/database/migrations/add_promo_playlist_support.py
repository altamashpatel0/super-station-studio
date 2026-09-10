from __future__ import annotations

from sqlalchemy import inspect, text


def _rebuild_playlist_tracks(engine) -> None:
    inspector = inspect(engine)
    if "playlist_tracks" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("playlist_tracks")}
    if "asset_id" in columns and any(c["name"] == "song_id" and c.get("nullable", True) for c in inspector.get_columns("playlist_tracks")):
        return

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("""
            CREATE TABLE playlist_tracks__promo_new (
                id INTEGER NOT NULL PRIMARY KEY,
                playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
                asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                added_at DATETIME NOT NULL,
                CHECK ((song_id IS NOT NULL AND asset_id IS NULL) OR (song_id IS NULL AND asset_id IS NOT NULL))
            )
        """))
        conn.execute(text("""
            INSERT INTO playlist_tracks__promo_new (id, playlist_id, song_id, asset_id, position, added_at)
            SELECT id, playlist_id, song_id, NULL, position, added_at
            FROM playlist_tracks
        """))
        conn.execute(text("DROP TABLE playlist_tracks"))
        conn.execute(text("ALTER TABLE playlist_tracks__promo_new RENAME TO playlist_tracks"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_tracks_playlist_id ON playlist_tracks (playlist_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_tracks_song_id ON playlist_tracks (song_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_tracks_asset_id ON playlist_tracks (asset_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_playlist_tracks_playlist_position ON playlist_tracks (playlist_id, position)"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def _rebuild_queue_items(engine) -> None:
    inspector = inspect(engine)
    if "queue_items" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("queue_items")}
    if "asset_id" in columns and any(c["name"] == "song_id" and c.get("nullable", True) for c in inspector.get_columns("queue_items")):
        return

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("""
            CREATE TABLE queue_items__promo_new (
                id INTEGER NOT NULL PRIMARY KEY,
                song_id INTEGER REFERENCES songs(id) ON DELETE CASCADE,
                asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                status VARCHAR NOT NULL,
                added_at DATETIME NOT NULL,
                CHECK ((song_id IS NOT NULL AND asset_id IS NULL) OR (song_id IS NULL AND asset_id IS NOT NULL))
            )
        """))
        conn.execute(text("""
            INSERT INTO queue_items__promo_new (id, song_id, asset_id, position, status, added_at)
            SELECT id, song_id, NULL, position, status, added_at
            FROM queue_items
        """))
        conn.execute(text("DROP TABLE queue_items"))
        conn.execute(text("ALTER TABLE queue_items__promo_new RENAME TO queue_items"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_queue_items_song_id ON queue_items (song_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_queue_items_asset_id ON queue_items (asset_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_queue_items_position ON queue_items (position)"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def upgrade_promo_playlist_support(engine) -> None:
    """Upgrade existing playlists/queue so a playlist occurrence can be a Song or Promo."""
    _rebuild_playlist_tracks(engine)
    _rebuild_queue_items(engine)
