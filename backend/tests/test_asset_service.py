"""
tests/test_asset_service.py
=============================

Service-level tests for `asset_service` (V0.5 Part 1): import
validation, duration detection via the real (unmodified) V0.1
`AudioDecoder`, and metadata update rules - independent of HTTP.
"""

from __future__ import annotations

import pytest

from app.services import asset_service
from app.services.asset_service import InvalidAssetError
from app.database.repositories.asset_repository import AssetNotFoundError, DuplicateAssetError
from src.models import AudioFileNotFoundError, DecodeError, UnsupportedFormatError


def test_import_jingle_sets_fields(db_session, make_asset_wav):
    path = make_asset_wav("jingle.wav", duration_seconds=1.0)
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="ID Sting", asset_type="JINGLE", category="ID"
    )
    assert asset.id is not None
    assert asset.name == "ID Sting"
    assert asset.asset_type == "JINGLE"
    assert asset.category == "ID"
    assert asset.enabled is True
    assert asset.duration == pytest.approx(1.0, abs=0.05)


def test_import_advertisement(db_session, make_asset_wav):
    path = make_asset_wav("ad.wav")
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="Local Ad", asset_type="ADVERTISEMENT"
    )
    assert asset.asset_type == "ADVERTISEMENT"


def test_duration_detected_correctly(db_session, make_asset_wav):
    path = make_asset_wav("timed.wav", duration_seconds=2.25)
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="Timed", asset_type="JINGLE"
    )
    assert asset.duration == pytest.approx(2.25, abs=0.05)


def test_import_missing_file_raises(db_session, tmp_path):
    missing = tmp_path / "nope.wav"
    with pytest.raises(AudioFileNotFoundError):
        asset_service.import_asset(
            db_session, file_path=str(missing), name="X", asset_type="JINGLE"
        )


def test_import_unsupported_extension_raises(db_session, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(UnsupportedFormatError):
        asset_service.import_asset(
            db_session, file_path=str(bad), name="X", asset_type="JINGLE"
        )


def test_import_corrupt_audio_raises(db_session, tmp_path):
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"garbage, not really audio data at all")
    with pytest.raises(DecodeError):
        asset_service.import_asset(
            db_session, file_path=str(corrupt), name="X", asset_type="JINGLE"
        )


def test_import_empty_name_raises(db_session, make_asset_wav):
    path = make_asset_wav("empty_name.wav")
    with pytest.raises(InvalidAssetError):
        asset_service.import_asset(
            db_session, file_path=str(path), name="   ", asset_type="JINGLE"
        )


def test_import_invalid_asset_type_raises(db_session, make_asset_wav):
    path = make_asset_wav("invalid_type.wav")
    with pytest.raises(InvalidAssetError):
        asset_service.import_asset(
            db_session, file_path=str(path), name="X", asset_type="MUSIC"
        )


def test_import_duplicate_file_path_raises(db_session, make_asset_wav):
    path = make_asset_wav("dup.wav")
    asset_service.import_asset(db_session, file_path=str(path), name="First", asset_type="JINGLE")
    with pytest.raises(DuplicateAssetError):
        asset_service.import_asset(
            db_session, file_path=str(path), name="Second", asset_type="JINGLE"
        )


def test_update_asset_metadata(db_session, make_asset_wav):
    path = make_asset_wav("update.wav")
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="Old", asset_type="JINGLE", category="Old"
    )
    updated = asset_service.update_asset(db_session, asset.id, name="New", category="New")
    assert updated.name == "New"
    assert updated.category == "New"


def test_update_missing_asset_raises(db_session):
    with pytest.raises(AssetNotFoundError):
        asset_service.update_asset(db_session, 999999, name="Nope")


def test_enable_disable_roundtrip(db_session, make_asset_wav):
    path = make_asset_wav("toggle.wav")
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="Toggle", asset_type="JINGLE"
    )
    disabled = asset_service.disable_asset(db_session, asset.id)
    assert disabled.enabled is False
    enabled = asset_service.enable_asset(db_session, asset.id)
    assert enabled.enabled is True


def test_list_assets_filters_by_type(db_session, make_asset_wav):
    asset_service.import_asset(
        db_session, file_path=str(make_asset_wav("j.wav")), name="J", asset_type="JINGLE"
    )
    asset_service.import_asset(
        db_session, file_path=str(make_asset_wav("ad.wav")), name="Ad", asset_type="ADVERTISEMENT"
    )
    jingles = asset_service.list_assets(db_session, asset_type="JINGLE")
    assert [a.name for a in jingles] == ["J"]


def test_delete_asset(db_session, make_asset_wav):
    path = make_asset_wav("delete.wav")
    asset = asset_service.import_asset(
        db_session, file_path=str(path), name="Delete Me", asset_type="JINGLE"
    )
    assert asset_service.delete_asset(db_session, asset.id) is True
    assert asset_service.get_asset(db_session, asset.id) is None
    assert asset_service.delete_asset(db_session, asset.id) is False
