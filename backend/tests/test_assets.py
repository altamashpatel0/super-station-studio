"""
tests/test_assets.py
======================

Covers V0.5 Part 2 (priority, cooldown_seconds, deterministic
ordering, metadata update) plus regression checks that V0.5 Part 1
behavior (category filtering, enable/disable, immutable duration) is
unaffected.
"""

from __future__ import annotations

import pytest

from app.services import asset_service
from app.services.asset_service import InvalidAssetError


# ----------------------------------------------------------------------
# priority
# ----------------------------------------------------------------------


def test_default_priority_is_zero(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("a.mp3"),
        name="Station ID",
        asset_type="JINGLE",
    )
    assert asset.priority == 0


def test_custom_priority_on_import(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("b.mp3"),
        name="Big Sale Ad",
        asset_type="ADVERTISEMENT",
        priority=5,
    )
    assert asset.priority == 5


# ----------------------------------------------------------------------
# cooldown_seconds
# ----------------------------------------------------------------------


def test_default_cooldown_is_zero(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("c.mp3"),
        name="Weather Jingle",
        asset_type="JINGLE",
    )
    assert asset.cooldown_seconds == 0


def test_custom_cooldown_on_import(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("d.mp3"),
        name="Car Dealership Ad",
        asset_type="ADVERTISEMENT",
        cooldown_seconds=120,
    )
    assert asset.cooldown_seconds == 120


def test_negative_cooldown_rejected_on_import(db_session, make_audio_file):
    with pytest.raises(InvalidAssetError):
        asset_service.import_asset(
            db_session,
            file_path=make_audio_file("e.mp3"),
            name="Bad Cooldown Ad",
            asset_type="ADVERTISEMENT",
            cooldown_seconds=-30,
        )


def test_negative_cooldown_rejected_on_update(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("f.mp3"),
        name="Traffic Jingle",
        asset_type="JINGLE",
    )
    with pytest.raises(InvalidAssetError):
        asset_service.update_asset(db_session, asset.id, cooldown_seconds=-1)


# ----------------------------------------------------------------------
# metadata update
# ----------------------------------------------------------------------


def test_metadata_update_changes_priority_and_cooldown(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("g.mp3"),
        name="Morning Jingle",
        asset_type="JINGLE",
    )
    updated = asset_service.update_asset(
        db_session, asset.id, priority=10, cooldown_seconds=60, category="Morning Show"
    )
    assert updated.priority == 10
    assert updated.cooldown_seconds == 60
    assert updated.category == "Morning Show"
    # untouched fields stay the same
    assert updated.name == "Morning Jingle"


# ----------------------------------------------------------------------
# priority ordering
# ----------------------------------------------------------------------


def test_priority_ordering(db_session, make_audio_file):
    low = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("low.mp3"),
        name="Zeta Ad",
        asset_type="ADVERTISEMENT",
        priority=1,
    )
    high = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("high.mp3"),
        name="Alpha Ad",
        asset_type="ADVERTISEMENT",
        priority=10,
    )
    mid = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("mid.mp3"),
        name="Beta Ad",
        asset_type="ADVERTISEMENT",
        priority=5,
    )

    ordered = asset_service.list_assets(db_session)
    ordered_ids = [a.id for a in ordered]
    assert ordered_ids == [high.id, mid.id, low.id]


def test_priority_ordering_falls_back_to_name_when_tied(db_session, make_audio_file):
    b = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("b_tied.mp3"),
        name="Bravo Jingle",
        asset_type="JINGLE",
        priority=3,
    )
    a = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("a_tied.mp3"),
        name="Alpha Jingle",
        asset_type="JINGLE",
        priority=3,
    )

    ordered = asset_service.list_assets(db_session)
    ordered_ids = [x.id for x in ordered]
    assert ordered_ids == [a.id, b.id]  # same priority -> alphabetical by name


# ----------------------------------------------------------------------
# category filtering (regression - still works)
# ----------------------------------------------------------------------


def test_category_filtering_still_works(db_session, make_audio_file):
    asset_service.import_asset(
        db_session,
        file_path=make_audio_file("news1.mp3"),
        name="News Jingle",
        asset_type="JINGLE",
        category="News",
        priority=2,
    )
    asset_service.import_asset(
        db_session,
        file_path=make_audio_file("sports1.mp3"),
        name="Sports Jingle",
        asset_type="JINGLE",
        category="Sports",
        priority=9,
    )

    news_only = asset_service.list_assets(db_session, category="News")
    assert len(news_only) == 1
    assert news_only[0].category == "News"


# ----------------------------------------------------------------------
# enabled/disabled behavior (regression - still works)
# ----------------------------------------------------------------------


def test_enable_disable_still_works(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("h.mp3"),
        name="Promo Ad",
        asset_type="ADVERTISEMENT",
    )
    assert asset.enabled is True

    disabled = asset_service.disable_asset(db_session, asset.id)
    assert disabled.enabled is False

    # still retrievable via GET while disabled
    fetched = asset_service.get_asset(db_session, asset.id)
    assert fetched is not None
    assert fetched.enabled is False

    # excluded from enabled_only listing
    enabled_only = asset_service.list_assets(db_session, enabled_only=True)
    assert asset.id not in [a.id for a in enabled_only]

    re_enabled = asset_service.enable_asset(db_session, asset.id)
    assert re_enabled.enabled is True


# ----------------------------------------------------------------------
# duration remains detected/read-only
# ----------------------------------------------------------------------


def test_duration_is_detected_on_import(db_session, make_audio_file):
    path = make_audio_file("i.mp3", size_bytes=1000)
    asset = asset_service.import_asset(
        db_session,
        file_path=path,
        name="Detected Duration Jingle",
        asset_type="JINGLE",
    )
    assert asset.duration == pytest.approx(10.0)  # stub decoder: size/100.0


def test_duration_not_editable_via_update(db_session, make_audio_file):
    asset = asset_service.import_asset(
        db_session,
        file_path=make_audio_file("j.mp3", size_bytes=500),
        name="Immutable Duration Ad",
        asset_type="ADVERTISEMENT",
    )
    original_duration = asset.duration

    # AssetUpdate / update_asset expose no duration parameter at all -
    # confirm the service signature can't take one, and that an update
    # to unrelated fields leaves duration untouched.
    with pytest.raises(TypeError):
        asset_service.update_asset(db_session, asset.id, duration=999)  # type: ignore[call-arg]

    updated = asset_service.update_asset(db_session, asset.id, name="Renamed Ad")
    assert updated.duration == original_duration
