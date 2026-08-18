"""
app/database/models.py
=======================

SQLAlchemy ORM models for the Music Library (V0.2) and, as of V0.3,
Playlists.

`songs` is deliberately flat (no separate artists/albums tables)
because normalizing further is not required for search/scan/stat
features, and keeping it flat keeps upserts on rescans simple.

`playlists` / `playlist_tracks` (V0.3) model a classic many-to-many
between playlists and songs, with `playlist_tracks.position` as the
join-row attribute that preserves track order within a playlist. A
song row can be referenced by any number of playlist_tracks rows
(across playlists, or more than once within the same playlist), and a
playlist can reference any number of songs.
"""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Song(Base):
    """One row per unique audio file on disk (unique by `file_path`)."""

    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity - `file_path` is the normalized absolute path and is the
    # single source of truth for de-duplication.
    file_path: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata (tags, with filename-derived fallbacks - see metadata_service.py)
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    artist: Mapped[str] = mapped_column(String, nullable=False, index=True)
    album: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    album_artist: Mapped[str] = mapped_column(String, nullable=False, default="")
    genre: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Technical info
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    format: Mapped[str] = mapped_column(String, nullable=False)

    # Library bookkeeping
    date_added: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    last_modified: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    last_played: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Soft-availability: a track missing from disk on refresh is disabled
    # rather than deleted, so history/play_count/id references survive.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        Index("ix_songs_artist_album", "artist", "album"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "genre": self.genre,
            "year": self.year,
            "track_number": self.track_number,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "file_size": self.file_size,
            "format": self.format,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "last_played": self.last_played.isoformat() if self.last_played else None,
            "play_count": self.play_count,
            "enabled": self.enabled,
        }


class ScannedFolder(Base):
    """
    Root folders the user has asked the library to watch.

    Recorded so `POST /api/library/rescan` can re-scan every previously
    imported folder without the caller having to remember/re-supply
    paths. Not exposed as its own CRUD surface in V0.2 - it's an
    implementation detail of the scan/rescan/refresh endpoints.
    """

    __tablename__ = "scanned_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folder_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    last_scanned: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class Playlist(Base):
    """A named, user-ordered collection of songs (V0.3)."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # `passive_deletes=True` defers to the DB's ON DELETE CASCADE
    # (rather than SQLAlchemy issuing per-row DELETEs) - see
    # PlaylistTrack.playlist_id below.
    tracks: Mapped[list["PlaylistTrack"]] = relationship(
        "PlaylistTrack",
        back_populates="playlist",
        order_by="PlaylistTrack.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self, *, include_tracks: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "track_count": len(self.tracks),
        }
        if include_tracks:
            data["tracks"] = [t.to_dict(include_song=True) for t in self.tracks]
        return data


class PlaylistTrack(Base):
    """
    One song's membership + position within one playlist (the join row
    of the playlists<->songs many-to-many relationship).

    Both foreign keys cascade on delete: removing a playlist drops its
    track rows, and hard-deleting a song (`SongRepository.delete`)
    removes it from any playlists it appeared in, so a playlist can
    never point at a song (or a deleted playlist) that no longer
    exists. This requires SQLite's per-connection FK enforcement to be
    turned on - see `database.py`.
    """

    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Dense, zero-based order within a playlist. Deliberately *not*
    # DB-uniqueness-constrained on (playlist_id, position): multi-row
    # reorders/inserts are easier to apply correctly as a single
    # renumbering pass in the repository than to sequence around a
    # unique index with SQLite's non-deferrable constraints.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="tracks")
    song: Mapped["Song"] = relationship("Song")

    __table_args__ = (
        Index("ix_playlist_tracks_playlist_position", "playlist_id", "position"),
    )

    def to_dict(self, *, include_song: bool = False) -> dict:
        data = {
            "id": self.id,
            "playlist_id": self.playlist_id,
            "song_id": self.song_id,
            "position": self.position,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }
        if include_song and self.song is not None:
            data["song"] = self.song.to_dict()
        return data


class AssetType(str, enum.Enum):
    """Kind of a Jingle/Advertisement Library asset (V0.5 Part 1).

    Deliberately just these two for V0.5 Part 1 - the library only
    stores/manages the audio, it does not yet know how or when either
    type gets played (that's automation/scheduler territory, V0.6+).
    """

    JINGLE = "JINGLE"
    ADVERTISEMENT = "ADVERTISEMENT"


class Asset(Base):
    """
    One row per imported Jingle/Advertisement audio file (V0.5 Part 1).

    Deliberately a separate table from `songs`: assets are a distinct
    library (station imaging / ad spots) with their own type and
    category, not part of the browsable Music Library, and Music
    Library rows must never be affected by asset operations (create,
    update, enable/disable, delete). Mirrors `Song`'s
    soft-availability pattern (`enabled`) and `Playlist`'s
    `created_at`/`updated_at` bookkeeping.

    V0.5 Part 2 adds two playback-management columns:

      - `priority` (int, default 0, higher = higher priority) - used
        by the Part 2 deterministic ordering (`priority` desc, then
        the existing `name` asc ordering).
      - `cooldown_seconds` (int, default 0, must not be negative) -
        validated at the schema/service layer; no scheduler/rotation
        logic reads it yet (out of scope for Part 2).

    Both are plain metadata columns, same as `category`/`description`
    - no automatic playback, scheduling, or rotation behavior is
    implied or implemented by their presence.
    """

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(
        SAEnum(AssetType, name="asset_type", native_enum=False, validate_strings=True),
        nullable=False,
        index=True,
    )

    # Identity - normalized absolute path, unique like `Song.file_path`
    # so the same file can't be imported into the asset library twice.
    file_path: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    category: Mapped[str] = mapped_column(String, nullable=False, default="", index=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")

    # Soft-availability, same rationale as `Song.enabled`: a disabled
    # asset is excluded from (future) automated playback selection but
    # stays in the database so history/references survive.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # --- V0.5 Part 2: playback-management metadata ---------------------
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    def to_dict(self) -> dict:
        asset_type = self.asset_type.value if isinstance(self.asset_type, AssetType) else self.asset_type
        return {
            "id": self.id,
            "name": self.name,
            "asset_type": asset_type,
            "file_path": self.file_path,
            "duration": self.duration,
            "category": self.category,
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority,
            "cooldown_seconds": self.cooldown_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class AssetPlaybackState(Base):
    """
    Runtime/history state for one Jingle or Advertisement asset.

    Kept in a separate table so V0.5 playback state does not alter the
    existing assets table or the V0.5 Part 1/Part 2 metadata contract.
    """

    __tablename__ = "asset_playback_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    state: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="IDLE",
        index=True,
    )

    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_played_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    failed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    stopped_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    play_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

class ScheduleTargetType(str, enum.Enum):
    """V0.6 Part 1 scheduler target types. Playback is out of scope here."""
    SONG = "SONG"
    JINGLE = "JINGLE"
    ADVERTISEMENT = "ADVERTISEMENT"
    PLAYLIST = "PLAYLIST"


class Schedule(Base):
    """V0.6 Part 1 schedule definition; contains no playback logic."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(
        SAEnum(
            ScheduleTargetType,
            name="schedule_target_type",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False, index=True)

    # Canonical form: ",0,2,4," where 0=Monday ... 6=Sunday.
    days_of_week: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=",0,1,2,3,4,5,6,",
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    def day_list(self) -> list[int]:
        if not self.days_of_week:
            return []
        return [
            int(value)
            for value in self.days_of_week.strip(",").split(",")
            if value
        ]

    def to_dict(self) -> dict:
        target_type = (
            self.target_type.value
            if isinstance(self.target_type, ScheduleTargetType)
            else self.target_type
        )
        return {
            "id": self.id,
            "name": self.name,
            "target_type": target_type,
            "target_id": self.target_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "days_of_week": self.day_list(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QueueItemStatus(str, enum.Enum):
    """Lifecycle of one item in the runtime Playback Queue (V0.3).

    Only `QUEUED` is ever set by the queue API itself (`add_track` /
    `add_playlist`). The rest exist so the (future) integration with
    the V0.1 AudioEngine has a place to record what actually happened
    to an item - this module never transitions an item into any of
    them on its own.
    """

    QUEUED = "QUEUED"
    PLAYING = "PLAYING"
    PLAYED = "PLAYED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class QueueItem(Base):
    """
    One song's slot in the single, global runtime playback queue
    (V0.3) - the "up next" list consumed by the (existing, unmodified)
    V0.1 `AudioEngine`.

    Unlike playlists, there is exactly one queue for the whole
    application (no `queue_id` - every row belongs to *the* queue), and
    `position` is a dense, zero-based order over every row in the
    table, maintained entirely by `QueueRepository` the same way
    `PlaylistTrack.position` is maintained by `PlaylistRepository`.

    `song_id` cascades on delete (`ON DELETE CASCADE`, enforced via
    SQLite's per-connection `PRAGMA foreign_keys=ON` - see
    `database.py`) so hard-deleting a song from the library also drops
    it from the queue, exactly like it does from playlists. The queue
    never stores or copies audio data - it only ever references an
    existing `songs.id`.
    """

    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Dense, zero-based order over the whole queue. Deliberately not
    # DB-uniqueness-constrained, for the same reason as
    # `PlaylistTrack.position`: multi-row reorders are easier to apply
    # correctly as a single renumbering pass in the repository than to
    # sequence around a unique index with SQLite's non-deferrable
    # constraints.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        SAEnum(QueueItemStatus, name="queue_item_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=QueueItemStatus.QUEUED.value,
    )

    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    song: Mapped["Song"] = relationship("Song")

    __table_args__ = (
        Index("ix_queue_items_position", "position"),
    )

    def to_dict(self, *, include_song: bool = False) -> dict:
        status_value = self.status.value if isinstance(self.status, QueueItemStatus) else self.status
        data = {
            "id": self.id,
            "song_id": self.song_id,
            "position": self.position,
            "status": status_value,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }
        if include_song and self.song is not None:
            data["song"] = self.song.to_dict()
        return data
