"""
queue_crossfade_manager.py
===========================

V0.4 Part 3: the final integration piece that connects the runtime
Playback Queue (`QueueSource`) to `TwoDeckEngine` + `CrossfadeController`,
so a queue plays end-to-end with automatic, gap-free crossfades between
consecutive tracks.

This module contains NO decode/transport/volume-ramp logic of its own
and creates NO additional audio engine - it only reacts to the
existing `Deck`/`AudioEngine` event hooks (`on_track_end`) and a
lightweight polling loop over `PlaybackStatus.position_seconds` /
`duration_seconds`, and drives `TwoDeckEngine` + `CrossfadeController`
through their existing public APIs. This mirrors exactly how the V0.3
`QueueManager` (`app/services/queue_manager.py`) drives the single-deck
V0.1 `AudioEngine` - `QueueCrossfadeManager` is the two-deck sibling of
that class, for callers that want automatic crossfading instead of a
hard cut between tracks.

Required flow (steady state)
-----------------------------
1. `current()` track plays on the active deck (A, say).
2. A lightweight monitor polls `active_deck.get_status()`. Once
   `duration_seconds - position_seconds <= crossfade_duration`:
     a. `peek_next()` is loaded into the *inactive* deck (B).
     b. `CrossfadeController.start(A, B, ...)` begins - this also
        starts deck B playing, per `CrossfadeController`'s own
        contract.
3. When the crossfade completes (`CrossfadeController.on_complete`):
     a. The active deck flips to B.
     b. `advance()` is called on the queue exactly once, moving its
        "current" pointer to the track that (per step 2a) is already
        playing on B - no reload, no duplicate playback.
     c. Deck A (now inactive) is stopped and is ready to receive
        whatever `peek_next()` returns next.

Manual stop / pause
--------------------
`Deck.stop()` (manual) fires `on_track_end(MANUAL_STOP)`. This module
treats that exactly like V0.3's `QueueManager` does: playback and
monitoring simply stop - the queue does **not** advance. `Deck.pause()`
does not fire `on_track_end` at all, and a paused deck is never
`PlayerState.PLAYING`, so the monitor's `remaining <= crossfade_duration`
check is naturally skipped while paused - a paused track can never
trigger a crossfade.

Short tracks
------------
If a track's total duration is shorter than the crossfade duration (or
the queue only discovers a next track very late), the monitor simply
starts the crossfade immediately, for whatever time actually remains.
If a track finishes completely before any crossfade could be started
at all (e.g. it completed between two poll ticks), the natural
`on_track_end(COMPLETED)` handler advances the queue and starts the
next track directly on the same deck, with no fade - i.e. it falls
back to the same hard-cut behaviour as V0.3's `QueueManager`, rather
than dropping the track.

Failure handling
-----------------
A `peek_next()` track that fails to load (missing/corrupt file) is
skipped via `QueueSource.skip_next()`, repeatedly, until a loadable
track is found or the queue is exhausted - mirroring V0.3's
"FAILED -> try the next QUEUED item" behaviour, just applied to the
deck used for crossfade preparation instead of the single V0.1 engine.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .crossfade import CrossfadeController, CrossfadeError, DEFAULT_CROSSFADE_DURATION_SECONDS
from .deck import Deck, DeckID, TwoDeckEngine
from .models import AudioEngineError, PlaybackStatus, PlayerState, TrackEndReason
from .queue_source import QueueSource, QueueTrack

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL_SECONDS = 0.1


class QueueCrossfadeManager:
    """Bridges a `QueueSource` to a `TwoDeckEngine`, automatically
    crossfading from one queued track into the next as each one nears
    its end."""

    def __init__(
        self,
        two_deck_engine: TwoDeckEngine,
        queue_source: QueueSource,
        crossfade_controller: Optional[CrossfadeController] = None,
        crossfade_duration_seconds: float = DEFAULT_CROSSFADE_DURATION_SECONDS,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._two_deck = two_deck_engine
        self._queue = queue_source
        self._crossfade_duration = float(crossfade_duration_seconds)
        self._poll_interval = float(poll_interval_seconds)
        self._crossfade = crossfade_controller or CrossfadeController(
            duration_seconds=self._crossfade_duration
        )
        self._crossfade.on_complete(self._on_crossfade_complete)

        self._lock = threading.RLock()
        self._active_deck_id: DeckID = DeckID.A
        self._play_token = 0
        self._crossfade_started_for_token: Optional[int] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        for deck_id in (DeckID.A, DeckID.B):
            deck = self._two_deck.get_deck(deck_id)
            deck.on_track_end(
                lambda reason, deck_id=deck_id: self._on_deck_track_end(deck_id, reason)
            )

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    @property
    def active_deck_id(self) -> DeckID:
        with self._lock:
            return self._active_deck_id

    @property
    def active_deck(self) -> Deck:
        with self._lock:
            return self._two_deck.get_deck(self._active_deck_id)

    def start(self) -> Optional[PlaybackStatus]:
        """Load and play `queue.current()` on the active deck (A, on a
        fresh manager) and begin monitoring for the next crossfade.
        Returns None (without starting anything) if the queue is
        empty."""
        with self._lock:
            self._active_deck_id = DeckID.A
            deck = self._two_deck.get_deck(self._active_deck_id)
            self._play_token += 1
            self._crossfade_started_for_token = None

        status = self._load_and_play_current(deck)
        if status is not None:
            self._start_monitor()
        return status

    def poll(self) -> None:
        """Run a single check: is the active deck close enough to the
        end of its track to start a crossfade into the next queued
        track? Safe to call directly (as the tests do, for
        determinism) or from the background monitor thread."""
        with self._lock:
            if self._crossfade.is_active():
                return

            deck_id = self._active_deck_id
            deck = self._two_deck.get_deck(deck_id)
            status = deck.get_status()

            if status.state != PlayerState.PLAYING:
                return  # paused / stopped / idle tracks never crossfade

            if self._crossfade_started_for_token == self._play_token:
                return  # already prepared/started this track's crossfade

            remaining = status.duration_seconds - status.position_seconds
            if remaining > self._crossfade_duration:
                return  # not close enough to the end yet

            next_track = self._queue.peek_next()
            if next_track is None:
                return  # nothing to crossfade into; let it finish naturally

            inactive_id = DeckID.B if deck_id == DeckID.A else DeckID.A
            inactive_deck = self._two_deck.get_deck(inactive_id)

            loaded_track = self._load_skipping_broken_next(inactive_deck)
            if loaded_track is None:
                return  # no playable upcoming track; finish naturally

            fade_duration = min(self._crossfade_duration, max(remaining, 0.0))
            self._crossfade_started_for_token = self._play_token
            try:
                self._crossfade.start(deck, inactive_deck, duration_seconds=fade_duration)
            except CrossfadeError:
                logger.exception("Failed to start automatic crossfade")
                self._crossfade_started_for_token = None

    def shutdown(self) -> None:
        """Cancel any active crossfade and stop the monitor. Safe to
        call at any time, including mid-crossfade, and safe to call
        more than once. Does not shut down the decks themselves - the
        caller still owns `TwoDeckEngine`'s lifecycle."""
        self._crossfade.cancel()
        self._stop_monitor()

    def __enter__(self) -> "QueueCrossfadeManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Internal: loading / advancing helpers
    # ------------------------------------------------------------------

    def _load_and_play_current(self, deck: Deck) -> Optional[PlaybackStatus]:
        """Load+play `queue.current()` on `deck`, skipping past any
        broken tracks via `skip_current()` until one plays or the
        queue is exhausted."""
        while True:
            track = self._queue.current()
            if track is None:
                self._stop_monitor()
                return None
            try:
                deck.load_track(track.file_path)
                return deck.play()
            except AudioEngineError:
                logger.warning("Queue track %r failed to load/play; skipping.", track.file_path)
                self._queue.skip_current()

    def _load_skipping_broken_next(self, deck: Deck) -> Optional[QueueTrack]:
        """Load `queue.peek_next()` into `deck`, skipping past broken
        upcoming tracks via `skip_next()` until one loads or the queue
        is exhausted."""
        track = self._queue.peek_next()
        while track is not None:
            try:
                deck.load_track(track.file_path)
                return track
            except AudioEngineError:
                logger.warning("Upcoming queue track %r is unplayable; skipping.", track.file_path)
                track = self._queue.skip_next()
        return None

    # ------------------------------------------------------------------
    # Internal: crossfade completion -> deck swap + queue advance
    # ------------------------------------------------------------------

    def _on_crossfade_complete(self, source_deck: Deck, target_deck: Deck) -> None:
        with self._lock:
            self._active_deck_id = target_deck.deck_id
            self._play_token += 1
            self._crossfade_started_for_token = None
            self._queue.advance()  # exactly once: matches what's already playing on target_deck
        try:
            source_deck.stop()
        except AudioEngineError:
            pass  # already stopped/idle - nothing to clean up

    # ------------------------------------------------------------------
    # Internal: track-end handling (manual stop / short-track fallback)
    # ------------------------------------------------------------------

    def _on_deck_track_end(self, deck_id: DeckID, reason: TrackEndReason) -> None:
        with self._lock:
            if deck_id != self._active_deck_id:
                return  # e.g. the deck we just crossfaded away from being stopped

            if reason == TrackEndReason.COMPLETED and self._crossfade.is_active():
                return  # _on_crossfade_complete() will handle advancing

        if reason == TrackEndReason.MANUAL_STOP:
            self._stop_monitor()
            return

        # COMPLETED (or ERROR) without an in-flight crossfade: the
        # track ended on its own (e.g. too short to ever cross the
        # crossfade-start threshold) - advance and continue, no fade.
        with self._lock:
            self._queue.advance()
            deck = self._two_deck.get_deck(self._active_deck_id)
            self._play_token += 1
            self._crossfade_started_for_token = None

        self._load_and_play_current(deck)

    # ------------------------------------------------------------------
    # Internal: background monitor thread
    # ------------------------------------------------------------------

    def _start_monitor(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event = threading.Event()
            thread = threading.Thread(
                target=self._monitor_loop,
                args=(self._stop_event,),
                name="QueueCrossfadeMonitor",
                daemon=True,
            )
            self._monitor_thread = thread
        thread.start()

    def _monitor_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.poll()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error while polling for automatic crossfade")
            if stop_event.wait(self._poll_interval):
                return

    def _stop_monitor(self) -> None:
        with self._lock:
            self._running = False
            stop_event = self._stop_event
            thread = self._monitor_thread
            self._monitor_thread = None
        stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
