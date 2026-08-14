"""Integration tests for `src.queue_crossfade_manager.QueueCrossfadeManager`
(V0.4 Part 3): the Queue <-> TwoDeckEngine <-> CrossfadeController glue.

Like `test_crossfade.py`, these use short, real crossfade durations and
the real background thread - nothing here fakes out time or threading.
`FakeAudioOutput` is used for all decks so no real audio hardware is
touched, and track *position* is advanced deterministically via
`pump()`, exactly as the rest of the suite already does.
"""

from __future__ import annotations

import struct
import time
import wave
from pathlib import Path

import pytest

from src.deck import DeckID, TwoDeckEngine
from src.models import PlayerState
from src.queue_crossfade_manager import QueueCrossfadeManager
from src.queue_source import InMemoryQueueSource, QueueTrack
from tests.fake_audio_output import FakeAudioOutput

SAMPLE_RATE = 8000


def _write_wav(path: Path, duration_seconds: float, sample_rate: int = SAMPLE_RATE) -> Path:
    n_frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack("<h", 0) * n_frames)
    return path


@pytest.fixture
def track_files(tmp_path: Path) -> list[Path]:
    """Three distinct 2.0s tracks, long enough that natural end-of-track
    never races with the (short, test-only) crossfade duration unless a
    test explicitly pumps close to the end."""
    return [
        _write_wav(tmp_path / f"track_{i}.wav", duration_seconds=2.0)
        for i in range(3)
    ]


@pytest.fixture
def short_track_file(tmp_path: Path) -> Path:
    """A track shorter than the crossfade duration used in tests."""
    return _write_wav(tmp_path / "short.wav", duration_seconds=0.1)


CROSSFADE_DURATION = 0.2  # seconds - short so the suite stays fast


@pytest.fixture
def two_deck(fake_output_a: FakeAudioOutput, fake_output_b: FakeAudioOutput) -> TwoDeckEngine:
    return TwoDeckEngine(deck_a_output=fake_output_a, deck_b_output=fake_output_b)


def _queue_of(*paths: Path) -> InMemoryQueueSource:
    return InMemoryQueueSource(
        [QueueTrack(id=i, file_path=str(p)) for i, p in enumerate(paths)]
    )


def _manager(two_deck: TwoDeckEngine, queue: InMemoryQueueSource) -> QueueCrossfadeManager:
    return QueueCrossfadeManager(
        two_deck,
        queue,
        crossfade_duration_seconds=CROSSFADE_DURATION,
        poll_interval_seconds=0.01,
    )


def _pump_to_remaining(fake_output: FakeAudioOutput, total_seconds: float, remaining_seconds: float) -> None:
    """Advance a track's position (via pump) so that exactly
    `remaining_seconds` of audio is left."""
    total_frames = int(total_seconds * SAMPLE_RATE)
    remaining_frames = int(remaining_seconds * SAMPLE_RATE)
    fake_output.pump(total_frames - remaining_frames)


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("Condition was not met within the timeout.")
        time.sleep(interval)


# ---------------------------------------------------------------------------
# 1. Queue track plays on Deck A
# ---------------------------------------------------------------------------


def test_queue_track_plays_on_deck_a(two_deck: TwoDeckEngine, track_files):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)

    status = manager.start()

    assert status.state == PlayerState.PLAYING
    assert status.file_path == str(track_files[0])
    assert manager.active_deck_id == DeckID.A
    manager.shutdown()


# ---------------------------------------------------------------------------
# 2. Next track loads on Deck B near track end
# ---------------------------------------------------------------------------


def test_next_track_loads_on_deck_b_near_end(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()

    assert two_deck.deck_b.get_status().file_path == str(track_files[1])
    manager.shutdown()


# ---------------------------------------------------------------------------
# 3. Automatic crossfade starts near track end
# ---------------------------------------------------------------------------


def test_automatic_crossfade_starts_near_track_end(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()

    assert manager._crossfade.is_active() is True
    manager.shutdown()


# ---------------------------------------------------------------------------
# 4 & 5. Deck A volume decreases / Deck B volume increases during crossfade
# ---------------------------------------------------------------------------


def test_deck_volumes_ramp_during_crossfade(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()
    assert manager._crossfade.is_active() is True

    time.sleep(CROSSFADE_DURATION / 2)

    assert 0.0 < two_deck.deck_a.get_volume() < 1.0
    assert 0.0 < two_deck.deck_b.get_volume() < 1.0
    assert two_deck.deck_a.get_volume() < 1.0
    assert two_deck.deck_b.get_volume() > 0.0

    manager.shutdown()


# ---------------------------------------------------------------------------
# 6 & 7. Deck B becomes active after crossfade; queue advances exactly once
# ---------------------------------------------------------------------------


def test_deck_b_becomes_active_and_queue_advances_exactly_once(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()
    assert manager._crossfade.is_active() is True

    _wait_until(lambda: not manager._crossfade.is_active())

    assert manager.active_deck_id == DeckID.B
    assert queue.current().file_path == str(track_files[1])
    # Exactly one advance: track 0 -> track 1, not further.
    assert queue.peek_next().file_path == str(track_files[2])

    manager.shutdown()


# ---------------------------------------------------------------------------
# 8. Three-track queue works A -> B -> A
# ---------------------------------------------------------------------------


def test_three_track_queue_alternates_decks_a_b_a(
    two_deck: TwoDeckEngine,
    track_files,
    fake_output_a: FakeAudioOutput,
    fake_output_b: FakeAudioOutput,
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()
    assert manager.active_deck_id == DeckID.A

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()
    _wait_until(lambda: not manager._crossfade.is_active())
    assert manager.active_deck_id == DeckID.B
    assert queue.current().file_path == str(track_files[1])

    _pump_to_remaining(fake_output_b, 2.0, remaining_seconds=0.1)
    manager.poll()
    _wait_until(lambda: not manager._crossfade.is_active())
    assert manager.active_deck_id == DeckID.A
    assert queue.current().file_path == str(track_files[2])

    manager.shutdown()


# ---------------------------------------------------------------------------
# 9. Single-track queue does not crossfade
# ---------------------------------------------------------------------------


def test_single_track_queue_does_not_crossfade(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(track_files[0])
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()

    # No next track exists, so no crossfade should ever start.
    assert manager._crossfade.is_active() is False
    assert two_deck.deck_b.get_status().file_path is None

    fake_output_a.drain(chunk_size=256)
    assert two_deck.deck_a.get_state() == PlayerState.STOPPED
    assert queue.current() is None

    manager.shutdown()


# ---------------------------------------------------------------------------
# 10. Manual stop does not advance the queue
# ---------------------------------------------------------------------------


def test_manual_stop_does_not_advance_queue(two_deck: TwoDeckEngine, track_files):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    two_deck.deck_a.stop()

    assert queue.current().file_path == str(track_files[0])
    assert two_deck.deck_b.get_status().file_path is None
    manager.shutdown()


# ---------------------------------------------------------------------------
# 11. Pause does not start a crossfade
# ---------------------------------------------------------------------------


def test_pause_does_not_start_crossfade(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    two_deck.deck_a.pause()
    manager.poll()

    assert manager._crossfade.is_active() is False
    assert two_deck.deck_b.get_status().file_path is None
    manager.shutdown()


# ---------------------------------------------------------------------------
# 12. Missing next track is handled safely
# ---------------------------------------------------------------------------


def test_missing_next_track_is_skipped_safely(
    two_deck: TwoDeckEngine, track_files, tmp_path: Path, fake_output_a: FakeAudioOutput
):
    missing_path = tmp_path / "does_not_exist.wav"
    queue = InMemoryQueueSource(
        [
            QueueTrack(id=0, file_path=str(track_files[0])),
            QueueTrack(id=1, file_path=str(missing_path)),
            QueueTrack(id=2, file_path=str(track_files[2])),
        ]
    )
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()

    # The broken track (id=1) must have been skipped in favor of the
    # next playable one, without crashing.
    assert manager._crossfade.is_active() is True
    assert two_deck.deck_b.get_status().file_path == str(track_files[2])

    _wait_until(lambda: not manager._crossfade.is_active())
    assert queue.current().file_path == str(track_files[2])

    manager.shutdown()


# ---------------------------------------------------------------------------
# 13. Short track (shorter than crossfade duration) is handled safely
# ---------------------------------------------------------------------------


def test_short_track_is_handled_safely(
    two_deck: TwoDeckEngine, short_track_file: Path, track_files, fake_output_a: FakeAudioOutput
):
    queue = InMemoryQueueSource(
        [
            QueueTrack(id=0, file_path=str(short_track_file)),
            QueueTrack(id=1, file_path=str(track_files[1])),
        ]
    )
    manager = _manager(two_deck, queue)
    manager.start()

    # The track (0.1s) is already shorter than the crossfade duration
    # (0.2s), so the very first poll should start the crossfade
    # immediately, for whatever time actually remains.
    manager.poll()

    assert manager._crossfade.is_active() is True
    _wait_until(lambda: not manager._crossfade.is_active())

    assert manager.active_deck_id == DeckID.B
    assert queue.current().file_path == str(track_files[1])

    manager.shutdown()


# ---------------------------------------------------------------------------
# 14. Shutdown during an active crossfade is safe
# ---------------------------------------------------------------------------


def test_shutdown_during_crossfade_is_safe(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)
    manager.poll()
    assert manager._crossfade.is_active() is True

    manager.shutdown()  # should not raise, block indefinitely, or crash

    assert manager._crossfade.is_active() is False
    two_deck.shutdown()


# ---------------------------------------------------------------------------
# Bonus: background monitor thread drives crossfading with no explicit
# poll() calls from the caller (proves the non-blocking, production path).
# ---------------------------------------------------------------------------


def test_background_monitor_triggers_crossfade_without_manual_poll(
    two_deck: TwoDeckEngine, track_files, fake_output_a: FakeAudioOutput
):
    queue = _queue_of(*track_files)
    manager = _manager(two_deck, queue)
    manager.start()

    _pump_to_remaining(fake_output_a, 2.0, remaining_seconds=0.1)

    _wait_until(lambda: manager._crossfade.is_active(), timeout=2.0)
    _wait_until(lambda: not manager._crossfade.is_active())

    assert manager.active_deck_id == DeckID.B
    manager.shutdown()
