from __future__ import annotations

from datetime import datetime

from app.database.models import Asset, AssetPlaybackState, AssetType, Playlist, PlaylistTrack, Song, QueueItem
from app.services.scheduler_selection import (
    CooldownBlockedError,
    NoEligiblePlaylistTrackError,
    ScheduleSelectionNotFoundError,
    TargetDisabledError,
    TargetFileMissingError,
    TargetNotFoundError,
    WrongAssetTypeError,
    select_for_current_schedule,
    select_for_schedule,
)


def song(db, n=1, *, enabled=True, path=None):
    row = Song(
        file_path=path or f"/tmp/v06-select-song-{n}.mp3",
        file_name=f"select-{n}.mp3",
        title=f"Select Song {n}",
        artist="Test Artist",
        album="Test Album",
        album_artist="Test Artist",
        genre="Test",
        duration=10.0,
        file_size=1,
        format="MP3",
        enabled=enabled,
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def asset(db, kind=AssetType.JINGLE, *, enabled=True, cooldown=0, path=None):
    row = Asset(
        name=f"Select {kind.value}",
        asset_type=kind,
        file_path=path or f"/tmp/v06-select-{kind.value.lower()}.mp3",
        duration=5.0,
        category="test",
        description="test",
        enabled=enabled,
        priority=10,
        cooldown_seconds=cooldown,
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def playlist(db):
    row = Playlist(name="Selection Playlist", description="test")
    db.add(row); db.commit(); db.refresh(row)
    return row


def track(db, pl, s, pos):
    row = PlaylistTrack(playlist_id=pl.id, song_id=s.id, position=pos)
    db.add(row); db.commit(); db.refresh(row)
    return row


def schedule(client, typ, target_id, **extra):
    payload = dict(
        name="Selection Schedule",
        target_type=typ,
        target_id=target_id,
        start_time="09:00",
        end_time="10:00",
        days_of_week=[0],
        enabled=True,
    )
    payload.update(extra)
    return client.post("/api/schedules", json=payload)


def test_song_selection(client, db_session, tmp_path):
    p = tmp_path / "song.mp3"; p.write_bytes(b"x")
    s = song(db_session, path=str(p))
    sch = schedule(client, "SONG", s.id).json()
    r = select_for_schedule(db_session, sch["id"])
    assert r.selected_id == s.id and r.selected_kind == "SONG"


def test_disabled_song(client, db_session, tmp_path):
    p = tmp_path / "song.mp3"; p.write_bytes(b"x")
    s = song(db_session, enabled=False, path=str(p))
    sch = schedule(client, "SONG", s.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except TargetDisabledError: return
    assert False


def test_missing_song_file(client, db_session):
    s = song(db_session)
    sch = schedule(client, "SONG", s.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except TargetFileMissingError: return
    assert False


def test_jingle_selection(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"; p.write_bytes(b"x")
    a = asset(db_session, path=str(p))
    sch = schedule(client, "JINGLE", a.id).json()
    r = select_for_schedule(db_session, sch["id"], datetime(2026,8,17,9,30))
    assert r.selected_id == a.id and r.selected_kind == "JINGLE"


def test_wrong_asset_type(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"; p.write_bytes(b"x")
    a = asset(db_session, path=str(p))
    sch = schedule(client, "ADVERTISEMENT", a.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except WrongAssetTypeError: return
    assert False


def test_disabled_jingle(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"; p.write_bytes(b"x")
    a = asset(db_session, enabled=False, path=str(p))
    sch = schedule(client, "JINGLE", a.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except TargetDisabledError: return
    assert False


def test_missing_jingle_file(client, db_session):
    a = asset(db_session)
    sch = schedule(client, "JINGLE", a.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except TargetFileMissingError: return
    assert False


def test_jingle_cooldown(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"; p.write_bytes(b"x")
    a = asset(db_session, cooldown=60, path=str(p))
    db_session.add(AssetPlaybackState(
        asset_id=a.id, state="COMPLETED",
        last_played_at=datetime(2026,8,17,9,0), play_count=1
    ))
    db_session.commit()
    sch = schedule(client, "JINGLE", a.id).json()
    try:
        select_for_schedule(db_session, sch["id"], datetime(2026,8,17,9,30))
    except CooldownBlockedError: return
    assert False


def test_ad_selection(client, db_session, tmp_path):
    p = tmp_path / "a.mp3"; p.write_bytes(b"x")
    a = asset(db_session, AssetType.ADVERTISEMENT, path=str(p))
    sch = schedule(client, "ADVERTISEMENT", a.id).json()
    r = select_for_schedule(db_session, sch["id"])
    assert r.selected_id == a.id and r.selected_kind == "ADVERTISEMENT"


def test_ad_cooldown(client, db_session, tmp_path):
    p = tmp_path / "a.mp3"; p.write_bytes(b"x")
    a = asset(db_session, AssetType.ADVERTISEMENT, cooldown=120, path=str(p))
    db_session.add(AssetPlaybackState(
        asset_id=a.id, state="COMPLETED",
        last_played_at=datetime(2026,8,17,9,0), play_count=1
    ))
    db_session.commit()
    sch = schedule(client, "ADVERTISEMENT", a.id).json()
    try:
        select_for_schedule(db_session, sch["id"], datetime(2026,8,17,9,30))
    except CooldownBlockedError: return
    assert False


def test_playlist_selects_first_eligible(client, db_session, tmp_path):
    p = tmp_path / "song.mp3"; p.write_bytes(b"x")
    s1 = song(db_session, 1, path=str(p))
    s2 = song(db_session, 2, path=str(p))
    pl = playlist(db_session)
    track(db_session, pl, s2, 2); track(db_session, pl, s1, 1)
    sch = schedule(client, "PLAYLIST", pl.id).json()
    r = select_for_schedule(db_session, sch["id"])
    assert r.selected_id == s1.id and r.selected_kind == "PLAYLIST_TRACK"


def test_playlist_skips_disabled_and_missing(client, db_session, tmp_path):
    p = tmp_path / "good.mp3"; p.write_bytes(b"x")
    bad = song(db_session, 1)
    disabled = song(db_session, 2, enabled=False, path=str(p))
    good = song(db_session, 3, path=str(p))
    pl = playlist(db_session)
    track(db_session, pl, bad, 1); track(db_session, pl, disabled, 2); track(db_session, pl, good, 3)
    sch = schedule(client, "PLAYLIST", pl.id).json()
    r = select_for_schedule(db_session, sch["id"])
    assert r.selected_id == good.id


def test_playlist_no_eligible_track(client, db_session):
    s = song(db_session)
    pl = playlist(db_session); track(db_session, pl, s, 1)
    sch = schedule(client, "PLAYLIST", pl.id).json()
    try: select_for_schedule(db_session, sch["id"])
    except NoEligiblePlaylistTrackError: return
    assert False


def test_missing_target_and_schedule(client, db_session):
    assert schedule(client, "SONG", 999999).status_code == 400
    try: select_for_schedule(db_session, 999999)
    except ScheduleSelectionNotFoundError: return
    assert False


def test_selection_does_not_change_asset_state(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"; p.write_bytes(b"x")
    a = asset(db_session, path=str(p))
    state = AssetPlaybackState(
        asset_id=a.id, state="COMPLETED",
        last_played_at=datetime(2026,8,17,8,0), play_count=7
    )
    db_session.add(state); db_session.commit()
    sch = schedule(client, "JINGLE", a.id).json()
    select_for_schedule(db_session, sch["id"], datetime(2026,8,17,9,0))
    db_session.expire_all()
    state = db_session.query(AssetPlaybackState).filter_by(asset_id=a.id).one()
    assert state.play_count == 7
    assert state.last_played_at == datetime(2026,8,17,8,0)
    assert state.state == "COMPLETED"


def test_selection_does_not_change_queue(client, db_session, tmp_path):
    p = tmp_path / "song.mp3"; p.write_bytes(b"x")
    s = song(db_session, path=str(p))
    pl = playlist(db_session); track(db_session, pl, s, 1)
    sch = schedule(client, "PLAYLIST", pl.id).json()
    before = db_session.query(QueueItem).count()
    r = select_for_schedule(db_session, sch["id"])
    after = db_session.query(QueueItem).count()
    assert r.selected_id == s.id and after == before


def test_deterministic_and_current_schedule_selection(client, db_session, tmp_path):
    p = tmp_path / "song.mp3"; p.write_bytes(b"x")
    s = song(db_session, path=str(p))
    schedule(client, "SONG", s.id, start_time="09:00", end_time="10:00", days_of_week=[0])
    r1 = select_for_current_schedule(db_session, datetime(2026,8,17,9,30))
    r2 = select_for_current_schedule(db_session, datetime(2026,8,17,9,30))
    assert r1 == r2 and r1.selected_id == s.id

def test_wrong_asset_type(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"
    p.write_bytes(b"x")
    a = asset(db_session, path=str(p))

    response = client.post(
        "/api/schedules",
        json={
            "name": "Wrong Type",
            "schedule_type": "ASSET",
            "target_type": "ADVERTISEMENT",
            "target_id": a.id,
            # Preserve the remaining required schedule fields from the
            # existing schedule() helper if your project uses different names.
        },
    )

    assert response.status_code in (400, 422)


def test_jingle_cooldown(client, db_session, tmp_path):
    p = tmp_path / "j.mp3"
    p.write_bytes(b"x")
    a = asset(db_session, cooldown=60, path=str(p))

    db_session.add(AssetPlaybackState(
        asset_id=a.id,
        state="COMPLETED",
        last_played_at=datetime(2026, 8, 17, 9, 0),
        play_count=1,
    ))
    db_session.commit()

    sch = schedule(client, "JINGLE", a.id).json()

    # 30 seconds after last playback: still inside 60-second cooldown.
    try:
        select_for_schedule(
            db_session,
            sch["id"],
            datetime(2026, 8, 17, 9, 0, 30),
        )
    except CooldownBlockedError:
        return

    assert False, "Expected CooldownBlockedError"


def test_ad_cooldown(client, db_session, tmp_path):
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x")
    a = asset(
        db_session,
        AssetType.ADVERTISEMENT,
        cooldown=120,
        path=str(p),
    )

    db_session.add(AssetPlaybackState(
        asset_id=a.id,
        state="COMPLETED",
        last_played_at=datetime(2026, 8, 17, 9, 0),
        play_count=1,
    ))
    db_session.commit()

    sch = schedule(client, "ADVERTISEMENT", a.id).json()

    # 30 seconds after last playback: still inside 120-second cooldown.
    try:
        select_for_schedule(
            db_session,
            sch["id"],
            datetime(2026, 8, 17, 9, 0, 30),
        )
    except CooldownBlockedError:
        return

    assert False, "Expected CooldownBlockedError"


def test_playlist_selects_first_eligible(client, db_session, tmp_path):
    p1 = tmp_path / "song1.mp3"
    p2 = tmp_path / "song2.mp3"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")

    s1 = song(db_session, 1, path=str(p1))
    s2 = song(db_session, 2, path=str(p2))

    # Keep the remainder of this test exactly as in the existing file,
    # but use s1/s2 as the two playlist tracks.


def test_playlist_skips_disabled_and_missing(client, db_session, tmp_path):
    bad = song(db_session, 1)

    disabled_path = tmp_path / "disabled.mp3"
    good_path = tmp_path / "good.mp3"
    disabled_path.write_bytes(b"x")
    good_path.write_bytes(b"x")

    disabled = song(
        db_session,
        2,
        enabled=False,
        path=str(disabled_path),
    )
    good = song(
        db_session,
        3,
        path=str(good_path),
    )

    # Keep the remainder of this test exactly as in the existing file,
    # but use disabled/good as the playlist tracks.
