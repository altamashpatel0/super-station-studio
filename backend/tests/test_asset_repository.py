"""
tests/test_asset_repository.py
================================

Repository-level tests for `AssetRepository` (V0.5 Part 1), mirroring
`test_playlist_repository.py`'s style: exercise the data-access layer
directly against an isolated sqlite session, without going through
HTTP or the audio decoder.
"""

from __future__ import annotations

import pytest

from app.database.repositories.asset_repository import (
    AssetNotFoundError,
    AssetRepository,
    DuplicateAssetError,
)


def _asset_data(**overrides):
    data = {
        "name": "Test Jingle",
        "asset_type": "JINGLE",
        "file_path": "/tmp/does-not-need-to-exist.wav",
        "duration": 3.5,
        "category": "ID",
        "description": "",
    }
    data.update(overrides)
    return data


def test_create_and_get_by_id(db_session):
    repo = AssetRepository(db_session)
    asset = repo.create(_asset_data())
    db_session.commit()

    fetched = repo.get_by_id(asset.id)
    assert fetched is not None
    assert fetched.name == "Test Jingle"
    assert fetched.asset_type == "JINGLE"


def test_create_duplicate_file_path_rejected(db_session):
    repo = AssetRepository(db_session)
    repo.create(_asset_data(file_path="/tmp/dup.wav"))
    db_session.commit()

    with pytest.raises(DuplicateAssetError):
        repo.create(_asset_data(name="Different Name", file_path="/tmp/dup.wav"))


def test_list_all(db_session):
    repo = AssetRepository(db_session)
    repo.create(_asset_data(name="A", file_path="/tmp/a.wav"))
    repo.create(_asset_data(name="B", file_path="/tmp/b.wav", asset_type="ADVERTISEMENT"))
    db_session.commit()

    all_assets = repo.list_all()
    assert {a.name for a in all_assets} == {"A", "B"}


def test_filter_by_type(db_session):
    repo = AssetRepository(db_session)
    repo.create(_asset_data(name="Jingle1", file_path="/tmp/j1.wav", asset_type="JINGLE"))
    repo.create(_asset_data(name="Ad1", file_path="/tmp/ad1.wav", asset_type="ADVERTISEMENT"))
    db_session.commit()

    jingles = repo.filter_by_type("JINGLE")
    assert [a.name for a in jingles] == ["Jingle1"]

    ads = repo.filter_by_type("ADVERTISEMENT")
    assert [a.name for a in ads] == ["Ad1"]


def test_filter_by_category(db_session):
    repo = AssetRepository(db_session)
    repo.create(_asset_data(name="Sports1", file_path="/tmp/sp1.wav", category="Sports"))
    repo.create(_asset_data(name="Weather1", file_path="/tmp/w1.wav", category="Weather"))
    db_session.commit()

    sports = repo.filter_by_category("Sports")
    assert [a.name for a in sports] == ["Sports1"]


def test_search(db_session):
    repo = AssetRepository(db_session)
    repo.create(_asset_data(name="Morning Show Sting", file_path="/tmp/m.wav"))
    repo.create(_asset_data(name="Evening Wrap", file_path="/tmp/e.wav"))
    db_session.commit()

    results = repo.search("morning")
    assert [a.name for a in results] == ["Morning Show Sting"]


def test_update(db_session):
    repo = AssetRepository(db_session)
    asset = repo.create(_asset_data())
    db_session.commit()

    updated = repo.update(asset.id, name="Renamed", category="NewCat")
    db_session.commit()
    assert updated.name == "Renamed"
    assert updated.category == "NewCat"


def test_update_missing_asset_raises(db_session):
    repo = AssetRepository(db_session)
    with pytest.raises(AssetNotFoundError):
        repo.update(999999, name="Nope")


def test_set_enabled(db_session):
    repo = AssetRepository(db_session)
    asset = repo.create(_asset_data())
    db_session.commit()

    disabled = repo.set_enabled(asset.id, False)
    db_session.commit()
    assert disabled.enabled is False

    enabled = repo.set_enabled(asset.id, True)
    db_session.commit()
    assert enabled.enabled is True


def test_delete(db_session):
    repo = AssetRepository(db_session)
    asset = repo.create(_asset_data())
    db_session.commit()

    assert repo.delete(asset.id) is True
    assert repo.get_by_id(asset.id) is None
    assert repo.delete(asset.id) is False


def test_delete_asset_does_not_touch_songs(db_session, make_song):
    song = make_song(title="Untouched")
    repo = AssetRepository(db_session)
    asset = repo.create(_asset_data())
    db_session.commit()

    repo.delete(asset.id)
    db_session.commit()

    from app.database.models import Song

    assert db_session.get(Song, song.id) is not None
