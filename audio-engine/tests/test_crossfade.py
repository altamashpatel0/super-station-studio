"""Tests for `src.crossfade.CrossfadeController` (V0.4 Part 2).

These tests use short crossfade durations (well under a second) so the
suite stays fast, but exercise the real background thread - nothing
here fakes out time or threading, since the whole point of the
controller is to prove it works without blocking the caller.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.crossfade import (
    CrossfadeAlreadyActiveError,
    CrossfadeController,
    CrossfadeCurve,
    CrossfadeError,
    InvalidCrossfadeError,
)
from src.deck import DeckID, TwoDeckEngine
from src.models import PlayerState
from tests.fake_audio_output import FakeAudioOutput


def _wait_until_inactive(controller: CrossfadeController, timeout: float = 2.0) -> None:
    """Poll from the *test* thread until the crossfade finishes, proving
    the controller itself never required the caller to block inside
    start()."""
    deadline = time.monotonic() + timeout
    while controller.is_active():
        if time.monotonic() > deadline:
            pytest.fail("Crossfade did not complete within the timeout.")
        time.sleep(0.01)


@pytest.fixture
def loaded_two_deck_engine(
    two_deck_engine: TwoDeckEngine, longer_wav_file: Path
) -> TwoDeckEngine:
    """Both decks loaded with a track long enough that natural
    end-of-track never interferes with crossfade timing."""
    two_deck_engine.deck_a.load_track(str(longer_wav_file))
    two_deck_engine.deck_b.load_track(str(longer_wav_file))
    return two_deck_engine


# ---------------------------------------------------------------------------
# 1. Crossfade starts correctly
# ---------------------------------------------------------------------------


def test_crossfade_starts_correctly(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.2)
    controller.start(deck_a, deck_b)

    assert controller.is_active() is True
    # The target deck must have been started automatically, since it
    # was not already playing.
    assert deck_b.get_state() == PlayerState.PLAYING

    _wait_until_inactive(controller)


# ---------------------------------------------------------------------------
# 2 & 3. Source volume decreases / target volume increases
# ---------------------------------------------------------------------------


def test_source_volume_decreases_and_target_volume_increases(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.2)
    controller.start(deck_a, deck_b)

    _wait_until_inactive(controller)

    assert deck_a.get_volume() == pytest.approx(0.0, abs=0.02)
    assert deck_b.get_volume() == pytest.approx(1.0, abs=0.02)


def test_source_volume_decreases_monotonically_partway_through(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.4)
    controller.start(deck_a, deck_b)

    samples = []
    for _ in range(4):
        time.sleep(0.06)
        samples.append(deck_a.get_volume())

    _wait_until_inactive(controller)

    # Non-increasing across the samples we took mid-fade (source only
    # ever fades out).
    assert all(earlier >= later - 1e-6 for earlier, later in zip(samples, samples[1:]))


# ---------------------------------------------------------------------------
# 4. Crossfade reaches completion
# ---------------------------------------------------------------------------


def test_crossfade_reaches_completion(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.15)
    controller.start(deck_a, deck_b)

    _wait_until_inactive(controller)

    assert controller.is_active() is False
    assert controller.progress() == pytest.approx(1.0, abs=1e-6)


def test_on_complete_listener_fires_on_natural_completion(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    completions = []
    controller = CrossfadeController(duration_seconds=0.1)
    controller.on_complete(lambda src, tgt: completions.append((src, tgt)))
    controller.start(deck_a, deck_b)

    _wait_until_inactive(controller)

    assert completions == [(deck_a, deck_b)]


# ---------------------------------------------------------------------------
# 5. Progress increases correctly
# ---------------------------------------------------------------------------


def test_progress_increases_correctly(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.3)
    assert controller.progress() == 0.0

    controller.start(deck_a, deck_b)

    samples = []
    for _ in range(4):
        time.sleep(0.05)
        samples.append(controller.progress())

    _wait_until_inactive(controller)
    samples.append(controller.progress())

    assert all(0.0 <= p <= 1.0 for p in samples)
    assert all(earlier <= later + 1e-6 for earlier, later in zip(samples, samples[1:]))
    assert samples[-1] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. Remaining time works
# ---------------------------------------------------------------------------


def test_remaining_time_works(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.3)
    assert controller.remaining_time() == 0.0  # nothing active yet

    controller.start(deck_a, deck_b)
    remaining_early = controller.remaining_time()
    assert remaining_early == pytest.approx(0.3, abs=0.1)

    time.sleep(0.15)
    remaining_mid = controller.remaining_time()
    assert 0.0 <= remaining_mid < remaining_early

    _wait_until_inactive(controller)
    assert controller.remaining_time() == 0.0


# ---------------------------------------------------------------------------
# 7. Custom duration works
# ---------------------------------------------------------------------------


def test_custom_duration_overrides_default(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=5.0)  # default, unused here
    start_time = time.monotonic()
    controller.start(deck_a, deck_b, duration_seconds=0.15)
    _wait_until_inactive(controller, timeout=2.0)
    elapsed = time.monotonic() - start_time

    # Actually took roughly the overridden duration, not the 5s default.
    assert elapsed < 1.0
    assert controller.default_duration == 5.0


@pytest.mark.parametrize("duration", [0.05, 0.1, 0.2])
def test_various_allowed_durations(
    loaded_two_deck_engine: TwoDeckEngine, duration: float
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=duration)
    controller.start(deck_a, deck_b)
    _wait_until_inactive(controller)

    assert deck_a.get_volume() == pytest.approx(0.0, abs=0.05)
    assert deck_b.get_volume() == pytest.approx(1.0, abs=0.05)


# ---------------------------------------------------------------------------
# 8. Cancel works
# ---------------------------------------------------------------------------


def test_cancel_stops_the_crossfade_cleanly(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=2.0)
    controller.start(deck_a, deck_b)
    assert controller.is_active() is True

    time.sleep(0.05)
    controller.cancel()

    assert controller.is_active() is False
    # Cancelled well before completion.
    assert controller.progress() < 1.0
    # Decks are left in a valid, non-crashed state.
    assert 0.0 <= deck_a.get_volume() <= 1.0
    assert 0.0 <= deck_b.get_volume() <= 1.0


def test_cancel_when_nothing_active_is_a_no_op(loaded_two_deck_engine: TwoDeckEngine):
    controller = CrossfadeController(duration_seconds=1.0)
    controller.cancel()  # must not raise
    assert controller.is_active() is False


def test_controller_can_be_reused_after_cancel(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=2.0)
    controller.start(deck_a, deck_b)
    controller.cancel()
    assert controller.is_active() is False

    # A fresh crossfade can start again afterwards.
    controller.start(deck_a, deck_b, duration_seconds=0.1)
    _wait_until_inactive(controller)
    assert deck_b.get_volume() == pytest.approx(1.0, abs=0.05)


# ---------------------------------------------------------------------------
# 9. Same deck is rejected
# ---------------------------------------------------------------------------


def test_same_deck_as_source_and_target_is_rejected(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.1)
    with pytest.raises(InvalidCrossfadeError):
        controller.start(deck_a, deck_a)

    assert controller.is_active() is False


# ---------------------------------------------------------------------------
# 10. Invalid duration is rejected
# ---------------------------------------------------------------------------


def test_negative_default_duration_is_rejected():
    with pytest.raises(InvalidCrossfadeError):
        CrossfadeController(duration_seconds=-1.0)


def test_negative_override_duration_is_rejected(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=1.0)
    with pytest.raises(InvalidCrossfadeError):
        controller.start(deck_a, deck_b, duration_seconds=-3.0)

    assert controller.is_active() is False


def test_non_numeric_duration_is_rejected():
    with pytest.raises(InvalidCrossfadeError):
        CrossfadeController(duration_seconds="five")  # type: ignore[arg-type]


def test_duration_zero_performs_an_instant_switch(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController()
    controller.start(deck_a, deck_b, duration_seconds=0.0)

    # Completes synchronously - no need to wait.
    assert controller.is_active() is False
    assert controller.progress() == pytest.approx(1.0, abs=1e-6)
    assert deck_a.get_volume() == pytest.approx(0.0, abs=1e-6)
    assert deck_b.get_volume() == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 11. Crossfade does not block the main thread
# ---------------------------------------------------------------------------


def test_start_returns_immediately_even_with_a_long_duration(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=5.0)

    call_start = time.monotonic()
    controller.start(deck_a, deck_b)
    call_elapsed = time.monotonic() - call_start

    assert call_elapsed < 0.5  # nowhere near the 5s crossfade duration
    assert controller.is_active() is True

    controller.cancel()  # don't leave a 5s thread running past the test


def test_crossfade_runs_on_a_background_thread(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.2)
    threads_before = {t.ident for t in threading.enumerate()}
    controller.start(deck_a, deck_b)
    threads_during = {t.ident for t in threading.enumerate()}

    assert threads_during - threads_before  # a new thread was spawned

    _wait_until_inactive(controller)


# ---------------------------------------------------------------------------
# 12. Existing deck playback remains functional
# ---------------------------------------------------------------------------


def test_existing_deck_playback_remains_functional_after_crossfade(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.1)
    controller.start(deck_a, deck_b)
    _wait_until_inactive(controller)

    # Ordinary AudioEngine-shaped API must still work normally on both
    # decks after a crossfade has completed.
    deck_b.pause()
    assert deck_b.get_state() == PlayerState.PAUSED
    deck_b.resume()
    assert deck_b.get_state() == PlayerState.PLAYING
    deck_b.stop()
    assert deck_b.get_state() == PlayerState.STOPPED

    deck_a.stop()
    assert deck_a.get_state() == PlayerState.STOPPED


# ---------------------------------------------------------------------------
# 13. Both decks remain independent
# ---------------------------------------------------------------------------


def test_decks_remain_independent_after_crossfade(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=0.1)
    controller.start(deck_a, deck_b)
    _wait_until_inactive(controller)

    deck_b.set_volume(0.4)
    assert deck_b.get_volume() == 0.4
    # Deck A's (post-crossfade, near-zero) volume must be untouched by
    # a change made directly to deck B.
    assert deck_a.get_volume() == pytest.approx(0.0, abs=0.02)

    deck_a.set_volume(0.7)
    assert deck_a.get_volume() == 0.7
    assert deck_b.get_volume() == 0.4


# ---------------------------------------------------------------------------
# 14. Shutdown during crossfade is safe
# ---------------------------------------------------------------------------


def test_shutdown_during_crossfade_is_safe(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=2.0)
    controller.start(deck_a, deck_b)
    assert controller.is_active() is True

    controller.shutdown()  # must not raise or hang

    assert controller.is_active() is False
    # Decks themselves are unharmed and can still be shut down cleanly.
    loaded_two_deck_engine.shutdown()


def test_context_manager_shuts_down_active_crossfade(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    with CrossfadeController(duration_seconds=2.0) as controller:
        controller.start(deck_a, deck_b)
        assert controller.is_active() is True

    assert controller.is_active() is False


# ---------------------------------------------------------------------------
# Additional edge cases: not-loaded decks, already active, target failure
# ---------------------------------------------------------------------------


def test_crossfade_already_active_is_rejected(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=2.0)
    controller.start(deck_a, deck_b)

    with pytest.raises(CrossfadeAlreadyActiveError):
        controller.start(deck_a, deck_b)

    controller.cancel()


def test_source_deck_not_loaded_is_rejected(
    two_deck_engine: TwoDeckEngine, longer_wav_file: Path
):
    # deck_a has nothing loaded; deck_b does.
    two_deck_engine.deck_b.load_track(str(longer_wav_file))

    controller = CrossfadeController(duration_seconds=0.1)
    with pytest.raises(InvalidCrossfadeError):
        controller.start(two_deck_engine.deck_a, two_deck_engine.deck_b)

    assert controller.is_active() is False


def test_target_deck_not_loaded_is_rejected(
    two_deck_engine: TwoDeckEngine, longer_wav_file: Path
):
    two_deck_engine.deck_a.load_track(str(longer_wav_file))
    two_deck_engine.deck_a.play()
    # deck_b has nothing loaded.

    controller = CrossfadeController(duration_seconds=0.1)
    with pytest.raises(InvalidCrossfadeError):
        controller.start(two_deck_engine.deck_a, two_deck_engine.deck_b)

    assert controller.is_active() is False


def test_target_deck_that_cannot_play_is_handled_without_crashing(
    two_deck_engine: TwoDeckEngine, longer_wav_file: Path
):
    from src.deck import Deck, DeckID

    two_deck_engine.deck_a.load_track(str(longer_wav_file))
    two_deck_engine.deck_a.play()

    # A target deck whose output device fails to open - play() will
    # raise, exactly the "target deck cannot play" edge case.
    failing_output = FakeAudioOutput(fail_on_open=True)
    broken_deck = Deck(DeckID.B, audio_output=failing_output)
    broken_deck.load_track(str(longer_wav_file))

    controller = CrossfadeController(duration_seconds=0.1)
    with pytest.raises(CrossfadeError):
        controller.start(two_deck_engine.deck_a, broken_deck)

    assert controller.is_active() is False
    # Deck A (the source) must be left completely unaffected.
    assert two_deck_engine.deck_a.get_state() == PlayerState.PLAYING
    assert two_deck_engine.deck_a.get_volume() == 1.0


def test_target_deck_already_playing_is_left_running_not_restarted(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()
    deck_b.play()
    deck_b.seek(0.5)

    controller = CrossfadeController(duration_seconds=0.1)
    controller.start(deck_a, deck_b)
    _wait_until_inactive(controller)

    # Because deck_b was already playing, start() must not have
    # restarted it (which would have reset its position to 0).
    assert deck_b.get_status().position_seconds >= 0.4


def test_equal_power_curve_is_available_and_reaches_full_swing(
    loaded_two_deck_engine: TwoDeckEngine,
):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(
        duration_seconds=0.15, curve=CrossfadeCurve.EQUAL_POWER
    )
    controller.start(deck_a, deck_b)
    _wait_until_inactive(controller)

    assert deck_a.get_volume() == pytest.approx(0.0, abs=0.02)
    assert deck_b.get_volume() == pytest.approx(1.0, abs=0.02)


def test_active_deck_and_target_deck_properties(loaded_two_deck_engine: TwoDeckEngine):
    deck_a = loaded_two_deck_engine.deck_a
    deck_b = loaded_two_deck_engine.deck_b
    deck_a.play()

    controller = CrossfadeController(duration_seconds=2.0)
    assert controller.active_deck is None
    assert controller.target_deck is None

    controller.start(deck_a, deck_b)
    assert controller.active_deck is deck_a
    assert controller.target_deck is deck_b

    controller.cancel()
    assert controller.active_deck is None
    assert controller.target_deck is None
