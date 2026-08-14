"""Tests for `src.deck.Deck` / `src.deck.TwoDeckEngine` (V0.4 foundation).

These tests deliberately mirror the shape of `test_engine.py` (each
deck IS an `AudioEngine`) but focus on the property that matters for
V0.4: two decks loaded into the same `TwoDeckEngine` must behave as
if they were two totally separate engines, right up until a future
`CrossfadeController` deliberately links their volumes together.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.deck import Deck, DeckID, TwoDeckEngine
from src.models import PlayerState, TrackEndReason
from tests.fake_audio_output import FakeAudioOutput


# ---------------------------------------------------------------------------
# 1. Deck A lifecycle
# ---------------------------------------------------------------------------


def test_deck_a_full_lifecycle(two_deck_engine: TwoDeckEngine, valid_wav_file: Path):
    deck_a = two_deck_engine.get_deck(DeckID.A)
    assert deck_a.deck_id == DeckID.A
    assert deck_a.get_state() == PlayerState.IDLE

    status = deck_a.load_track(str(valid_wav_file))
    assert status.state == PlayerState.STOPPED

    status = deck_a.play()
    assert status.state == PlayerState.PLAYING

    status = deck_a.pause()
    assert status.state == PlayerState.PAUSED

    status = deck_a.resume()
    assert status.state == PlayerState.PLAYING

    status = deck_a.stop()
    assert status.state == PlayerState.STOPPED
    assert status.position_seconds == 0


# ---------------------------------------------------------------------------
# 2. Deck B lifecycle
# ---------------------------------------------------------------------------


def test_deck_b_full_lifecycle(two_deck_engine: TwoDeckEngine, valid_wav_file: Path):
    deck_b = two_deck_engine.get_deck(DeckID.B)
    assert deck_b.deck_id == DeckID.B
    assert deck_b.get_state() == PlayerState.IDLE

    status = deck_b.load_track(str(valid_wav_file))
    assert status.state == PlayerState.STOPPED

    status = deck_b.play()
    assert status.state == PlayerState.PLAYING

    status = deck_b.pause()
    assert status.state == PlayerState.PAUSED

    status = deck_b.resume()
    assert status.state == PlayerState.PLAYING

    status = deck_b.stop()
    assert status.state == PlayerState.STOPPED
    assert status.position_seconds == 0


# ---------------------------------------------------------------------------
# 3. Both decks loaded independently (different files)
# ---------------------------------------------------------------------------


def test_both_decks_loaded_independently_with_different_files(
    two_deck_engine: TwoDeckEngine, valid_wav_file: Path, longer_wav_file: Path
):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(longer_wav_file))

    status_a = two_deck_engine.deck_a.get_status()
    status_b = two_deck_engine.deck_b.get_status()

    assert status_a.file_path == str(valid_wav_file)
    assert status_b.file_path == str(longer_wav_file)
    assert status_a.duration_seconds != status_b.duration_seconds
    assert status_a.duration_seconds == pytest.approx(0.5, abs=0.05)
    assert status_b.duration_seconds == pytest.approx(2.0, abs=0.05)


def test_decks_use_distinct_output_devices(
    two_deck_engine: TwoDeckEngine,
    fake_output_a: FakeAudioOutput,
    fake_output_b: FakeAudioOutput,
    valid_wav_file: Path,
):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))

    two_deck_engine.deck_a.play()
    assert fake_output_a.opened is True
    assert fake_output_b.opened is False

    two_deck_engine.deck_b.play()
    assert fake_output_b.opened is True


# ---------------------------------------------------------------------------
# 4. Independent pause/resume
# ---------------------------------------------------------------------------


def test_independent_pause_resume(
    two_deck_engine: TwoDeckEngine, valid_wav_file: Path
):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))

    two_deck_engine.deck_a.play()
    two_deck_engine.deck_b.play()

    two_deck_engine.deck_a.pause()

    assert two_deck_engine.deck_a.get_state() == PlayerState.PAUSED
    # Deck B must be unaffected by deck A's pause.
    assert two_deck_engine.deck_b.get_state() == PlayerState.PLAYING

    two_deck_engine.deck_a.resume()
    assert two_deck_engine.deck_a.get_state() == PlayerState.PLAYING
    assert two_deck_engine.deck_b.get_state() == PlayerState.PLAYING


# ---------------------------------------------------------------------------
# 5. Independent seek
# ---------------------------------------------------------------------------


def test_independent_seek(two_deck_engine: TwoDeckEngine, longer_wav_file: Path):
    two_deck_engine.deck_a.load_track(str(longer_wav_file))
    two_deck_engine.deck_b.load_track(str(longer_wav_file))

    two_deck_engine.deck_a.seek(1.5)
    two_deck_engine.deck_b.seek(0.3)

    status_a = two_deck_engine.deck_a.get_status()
    status_b = two_deck_engine.deck_b.get_status()

    assert status_a.position_seconds == pytest.approx(1.5, abs=0.05)
    assert status_b.position_seconds == pytest.approx(0.3, abs=0.05)


# ---------------------------------------------------------------------------
# 6. Independent volume
# ---------------------------------------------------------------------------


def test_independent_volume(two_deck_engine: TwoDeckEngine, valid_wav_file: Path):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))

    two_deck_engine.deck_a.set_volume(0.2)
    two_deck_engine.deck_b.set_volume(0.9)

    assert two_deck_engine.deck_a.get_volume() == 0.2
    assert two_deck_engine.deck_b.get_volume() == 0.9

    # Changing one deck's volume again must not disturb the other -
    # this is the exact independence a future CrossfadeController
    # will rely on when ramping both decks' volumes on a timer.
    two_deck_engine.deck_a.set_volume(0.6)
    assert two_deck_engine.deck_a.get_volume() == 0.6
    assert two_deck_engine.deck_b.get_volume() == 0.9


# ---------------------------------------------------------------------------
# 7. Track completion (per-deck)
# ---------------------------------------------------------------------------


def test_track_completion_fires_only_for_the_completing_deck(
    two_deck_engine: TwoDeckEngine,
    fake_output_a: FakeAudioOutput,
    fake_output_b: FakeAudioOutput,
    valid_wav_file: Path,
    longer_wav_file: Path,
):
    a_completed = []
    b_completed = []
    two_deck_engine.deck_a.on_track_complete(a_completed.append)
    two_deck_engine.deck_b.on_track_complete(b_completed.append)

    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(longer_wav_file))

    two_deck_engine.deck_a.play()
    two_deck_engine.deck_b.play()

    # Only drain deck A to completion; deck B keeps playing.
    fake_output_a.drain(chunk_size=256)

    assert a_completed == [str(valid_wav_file)]
    assert b_completed == []
    assert two_deck_engine.deck_a.get_state() == PlayerState.STOPPED
    assert two_deck_engine.deck_b.get_state() == PlayerState.PLAYING


def test_track_end_reason_is_per_deck(
    two_deck_engine: TwoDeckEngine,
    fake_output_a: FakeAudioOutput,
    valid_wav_file: Path,
):
    reasons_a = []
    reasons_b = []
    two_deck_engine.deck_a.on_track_end(reasons_a.append)
    two_deck_engine.deck_b.on_track_end(reasons_b.append)

    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))

    two_deck_engine.deck_a.play()
    two_deck_engine.deck_b.play()

    fake_output_a.drain(chunk_size=256)

    assert reasons_a == [TrackEndReason.COMPLETED]
    assert reasons_b == []


# ---------------------------------------------------------------------------
# 8. One deck stopping must not affect the other
# ---------------------------------------------------------------------------


def test_stopping_one_deck_does_not_affect_the_other(
    two_deck_engine: TwoDeckEngine, valid_wav_file: Path
):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))

    two_deck_engine.deck_a.play()
    two_deck_engine.deck_b.play()
    two_deck_engine.deck_b.seek  # sanity: attribute exists, not called here

    two_deck_engine.deck_a.stop()

    status_a = two_deck_engine.deck_a.get_status()
    status_b = two_deck_engine.deck_b.get_status()

    assert status_a.state == PlayerState.STOPPED
    assert status_a.position_seconds == 0
    # Deck B must still be playing, untouched by deck A's stop().
    assert status_b.state == PlayerState.PLAYING


def test_shutdown_one_deck_leaves_other_deck_object_intact(
    two_deck_engine: TwoDeckEngine,
    fake_output_a: FakeAudioOutput,
    fake_output_b: FakeAudioOutput,
    valid_wav_file: Path,
):
    two_deck_engine.deck_a.load_track(str(valid_wav_file))
    two_deck_engine.deck_b.load_track(str(valid_wav_file))
    two_deck_engine.deck_a.play()
    two_deck_engine.deck_b.play()

    two_deck_engine.deck_a.shutdown()

    assert fake_output_a.closed is True
    assert fake_output_b.closed is False
    assert two_deck_engine.deck_b.get_state() == PlayerState.PLAYING


# ---------------------------------------------------------------------------
# TwoDeckEngine plumbing
# ---------------------------------------------------------------------------


def test_get_deck_returns_correct_instances(two_deck_engine: TwoDeckEngine):
    assert two_deck_engine.get_deck(DeckID.A) is two_deck_engine.deck_a
    assert two_deck_engine.get_deck(DeckID.B) is two_deck_engine.deck_b
    assert two_deck_engine.get_deck(DeckID.A) is not two_deck_engine.get_deck(DeckID.B)


def test_decks_property_exposes_both(two_deck_engine: TwoDeckEngine):
    decks = two_deck_engine.decks
    assert set(decks.keys()) == {DeckID.A, DeckID.B}
    assert decks[DeckID.A] is two_deck_engine.deck_a
    assert decks[DeckID.B] is two_deck_engine.deck_b


def test_context_manager_shuts_down_both_decks(
    fake_output_a: FakeAudioOutput, fake_output_b: FakeAudioOutput, valid_wav_file: Path
):
    with TwoDeckEngine(deck_a_output=fake_output_a, deck_b_output=fake_output_b) as two_deck:
        two_deck.deck_a.load_track(str(valid_wav_file))
        two_deck.deck_b.load_track(str(valid_wav_file))
        two_deck.deck_a.play()
        two_deck.deck_b.play()

    assert fake_output_a.closed is True
    assert fake_output_b.closed is True


def test_deck_is_an_audio_engine_backward_compatible_api(
    two_deck_engine: TwoDeckEngine, valid_wav_file: Path
):
    """Every deck must still be usable via the exact same API surface
    as a plain V0.1 `AudioEngine`, for backward compatibility with any
    existing code (including V0.2/V0.3) written against `AudioEngine`."""
    from src.engine import AudioEngine

    deck_a = two_deck_engine.get_deck(DeckID.A)
    assert isinstance(deck_a, AudioEngine)
    assert isinstance(deck_a, Deck)

    # Full AudioEngine-shaped call sequence.
    status = deck_a.load_track(str(valid_wav_file))
    assert status.to_dict()["state"] == "STOPPED"
    deck_a.play()
    deck_a.set_volume(0.4)
    assert deck_a.get_volume() == 0.4
    deck_a.pause()
    deck_a.resume()
    deck_a.stop()
