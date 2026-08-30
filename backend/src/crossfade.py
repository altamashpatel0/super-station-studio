"""
crossfade.py
============

V0.4 Part 2: `CrossfadeController` - smoothly transitions playback
between two existing `Deck` instances by ramping their independent
`volume` (inherited from `AudioEngine`/`Player`) over a configurable
duration.

Design intent
--------------
This module deliberately does **not** implement another audio engine.
It only *drives* the volume knobs that already exist on `Deck`
(`set_volume` / `get_volume`, inherited unchanged from `AudioEngine`).
Because each `Deck` owns its own `Player` and `AudioOutputBase` (see
`deck.py`), ramping deck A's volume down while ramping deck B's volume
up cannot cross-contaminate either deck's internal state - the
controller is purely an external orchestrator.

Non-blocking
------------
The volume ramp runs on a dedicated background `threading.Thread`
(daemon, so it never prevents process exit) that wakes up on a short,
fixed tick interval to update both decks' volumes and then goes back
to sleep. `start()` itself returns immediately - it only validates
inputs, optionally starts the target deck, and spawns the thread.

Cancellation-safety
--------------------
`cancel()` (and `shutdown()`) signal a `threading.Event` and join the
background thread with a bounded timeout. The tick loop checks that
event on every iteration and exits promptly, leaving whatever volumes
the decks currently have - it never "snaps" the decks to a final
value on cancellation, and it never lets an exception from a deck
propagate out and crash the thread or the caller.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from enum import Enum
from typing import Callable, List, Optional, Tuple

from .deck import Deck
from .models import AudioEngineError

logger = logging.getLogger(__name__)

# Not hard-coded into the transition logic itself - this is only the
# *default* used when a caller does not specify a duration.
DEFAULT_CROSSFADE_DURATION_SECONDS = 5.0

# How often the background thread wakes up to update volumes. Small
# enough to be perceptually smooth, large enough not to busy-loop.
_TICK_INTERVAL_SECONDS = 0.02

# Bound on how long cancel()/shutdown() will wait for the background
# thread to notice the cancellation and exit, so a hung deck callback
# can never make cancel() block forever.
_JOIN_TIMEOUT_SECONDS = 2.0


class CrossfadeCurve(str, Enum):
    """How volume is interpolated across the crossfade's progress."""

    #: Straight line: source 1.0->0.0, target 0.0->1.0. Simple and
    #: predictable; the default.
    LINEAR = "LINEAR"

    #: Equal-power (constant perceived loudness) curve using
    #: sin/cos, which avoids the brief perceived "dip" in volume
    #: that a linear crossfade can produce for uncorrelated program
    #: material. Optional, for callers that want it.
    EQUAL_POWER = "EQUAL_POWER"


class CrossfadeError(AudioEngineError):
    """Base class for all crossfade-specific errors."""


class InvalidCrossfadeError(CrossfadeError):
    """Raised for malformed crossfade requests: same deck used as both
    source and target, an invalid duration, or a deck that is not in
    a state a crossfade can be started from."""


class CrossfadeAlreadyActiveError(CrossfadeError):
    """Raised when `start()` is called while a crossfade is already
    in progress. Call `cancel()` first (or wait for completion)."""


def _compute_volumes(t: float, curve: CrossfadeCurve) -> Tuple[float, float]:
    """Return (source_volume, target_volume) for progress `t` in [0, 1]."""
    t = min(max(t, 0.0), 1.0)
    if curve == CrossfadeCurve.EQUAL_POWER:
        source_volume = math.cos(t * (math.pi / 2.0))
        target_volume = math.sin(t * (math.pi / 2.0))
    else:  # LINEAR
        source_volume = 1.0 - t
        target_volume = t
    # Guard against floating point drift landing just outside [0, 1],
    # which would otherwise trip Deck.set_volume()'s validation.
    source_volume = min(max(source_volume, 0.0), 1.0)
    target_volume = min(max(target_volume, 0.0), 1.0)
    return source_volume, target_volume


class CrossfadeController:
    """
    Drives a smooth volume crossfade between two `Deck` instances.

    One `CrossfadeController` can be reused for multiple, sequential
    crossfades (it is not tied to a specific pair of decks at
    construction time) - only one crossfade may be active at a time.
    """

    def __init__(
        self,
        duration_seconds: float = DEFAULT_CROSSFADE_DURATION_SECONDS,
        curve: CrossfadeCurve = CrossfadeCurve.LINEAR,
    ) -> None:
        """
        Args:
            duration_seconds: Default crossfade duration, in seconds,
                used whenever `start()` is called without an explicit
                override. Must be >= 0.
            curve: Default volume-interpolation curve.
        """
        self._validate_duration(duration_seconds)
        self._default_duration = float(duration_seconds)
        self._curve = curve

        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()

        self._active = False
        self._source_deck: Optional[Deck] = None
        self._target_deck: Optional[Deck] = None
        self._duration = self._default_duration
        self._start_time: Optional[float] = None
        self._progress = 0.0

        self._on_complete_listeners: List[Callable[[Deck, Deck], None]] = []

    # ------------------------------------------------------------------
    # Public configuration
    # ------------------------------------------------------------------

    @property
    def default_duration(self) -> float:
        return self._default_duration

    @property
    def curve(self) -> CrossfadeCurve:
        return self._curve

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def progress(self) -> float:
        """Fraction of the current (or most recently finished/cancelled)
        crossfade completed, in [0.0, 1.0]. 0.0 if none has run yet."""
        with self._lock:
            return self._progress

    def remaining_time(self) -> float:
        """Seconds remaining in the active crossfade. 0.0 if no
        crossfade is currently active."""
        with self._lock:
            if not self._active or self._start_time is None:
                return 0.0
            elapsed = time.monotonic() - self._start_time
            return max(self._duration - elapsed, 0.0)

    @property
    def active_deck(self) -> Optional[Deck]:
        """The deck currently fading OUT (the "source"/currently
        active deck), or None if no crossfade is active."""
        with self._lock:
            return self._source_deck if self._active else None

    @property
    def source_deck(self) -> Optional[Deck]:
        with self._lock:
            return self._source_deck if self._active else None

    @property
    def target_deck(self) -> Optional[Deck]:
        """The deck currently fading IN, or None if no crossfade is
        active."""
        with self._lock:
            return self._target_deck if self._active else None

    def on_complete(self, callback: Callable[[Deck, Deck], None]) -> None:
        """Register a callback invoked as `callback(source_deck,
        target_deck)` when a crossfade finishes *naturally* (reaches
        100%). Not invoked on cancellation."""
        self._on_complete_listeners.append(callback)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(
        self,
        source_deck: Deck,
        target_deck: Deck,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """
        Begin crossfading from `source_deck` to `target_deck`.

        Returns immediately; the actual volume ramp runs on a
        background thread. Raises synchronously (before any thread is
        started, and without touching either deck) for malformed
        requests.

        Raises:
            CrossfadeAlreadyActiveError: a crossfade is already running.
            InvalidCrossfadeError: `source_deck is target_deck`, the
                duration is invalid, or a deck is not loaded.
            CrossfadeError: the target deck could not be started.
        """
        with self._lock:
            if self._active:
                raise CrossfadeAlreadyActiveError(
                    "A crossfade is already active. Call cancel() first, "
                    "or wait for it to complete."
                )

            if source_deck is target_deck:
                raise InvalidCrossfadeError(
                    "source_deck and target_deck must be different decks."
                )

            duration = (
                self._default_duration if duration_seconds is None else duration_seconds
            )
            self._validate_duration(duration)

            source_status = source_deck.get_status()
            if source_status.file_path is None:
                raise InvalidCrossfadeError(
                    "source_deck has no track loaded; cannot crossfade "
                    "away from an empty deck."
                )

            target_status = target_deck.get_status()
            if target_status.file_path is None:
                raise InvalidCrossfadeError(
                    "target_deck has no track loaded; cannot crossfade "
                    "into an empty deck."
                )

            # Make sure the target deck is actually producing audio
            # before we start ramping its volume up. If it is already
            # playing, leave it alone. Otherwise (a very common real
            # use-case: the next track is cued up but not yet
            # started), start it for the caller.
            if not target_deck.is_playing():
                try:
                    target_deck.play()
                except Exception as exc:
                    raise CrossfadeError(
                        f"target_deck could not be started for crossfade: {exc}"
                    ) from exc

            self._source_deck = source_deck
            self._target_deck = target_deck
            self._duration = float(duration)
            self._cancel_event = threading.Event()

            if duration == 0.0:
                # Instant switch - no need for a background thread.
                self._apply_volumes_safely(source_deck, target_deck, 1.0)
                self._active = True
                self._progress = 1.0
                self._start_time = time.monotonic()
                self._finish_locked(cancelled=False)
                return

            self._active = True
            self._progress = 0.0
            self._start_time = time.monotonic()

            thread = threading.Thread(
                target=self._run,
                args=(source_deck, target_deck, self._duration, self._cancel_event),
                name="CrossfadeController",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def cancel(self) -> None:
        """
        Cancel an in-progress crossfade, leaving both decks at
        whatever volume they currently have. Safe to call even if no
        crossfade is active (no-op).
        """
        with self._lock:
            if not self._active:
                return
            self._cancel_event.set()
            thread = self._thread

        # Join outside the lock: the background thread also needs the
        # lock briefly on each tick, so holding it here would deadlock.
        if thread is not None:
            thread.join(timeout=_JOIN_TIMEOUT_SECONDS)

        with self._lock:
            if self._active:
                self._finish_locked(cancelled=True)

    def shutdown(self) -> None:
        """
        Tear down the controller: cancel any active crossfade and
        release the background thread. Safe to call multiple times and
        safe to call during an active crossfade.
        """
        self.cancel()

    def __enter__(self) -> "CrossfadeController":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Internal: background thread
    # ------------------------------------------------------------------

    def _run(
        self,
        source_deck: Deck,
        target_deck: Deck,
        duration: float,
        cancel_event: threading.Event,
    ) -> None:
        try:
            start_time = time.monotonic()
            while True:
                if cancel_event.is_set():
                    return  # cancel() itself finalizes state.

                elapsed = time.monotonic() - start_time
                t = min(elapsed / duration, 1.0) if duration > 0 else 1.0

                self._apply_volumes_safely(source_deck, target_deck, t)

                with self._lock:
                    # A cancel() that raced in between our check above
                    # and now still wins - don't overwrite its result.
                    if not self._active:
                        return
                    self._progress = t

                if t >= 1.0:
                    with self._lock:
                        if self._active:
                            self._finish_locked(cancelled=False)
                    return

                if cancel_event.wait(_TICK_INTERVAL_SECONDS):
                    return
        except Exception:  # pragma: no cover - defensive; must never crash
            logger.exception("Unexpected error in crossfade background thread")
            with self._lock:
                if self._active:
                    self._finish_locked(cancelled=True)

    def _apply_volumes_safely(self, source_deck: Deck, target_deck: Deck, t: float) -> None:
        source_volume, target_volume = _compute_volumes(t, self._curve)
        for deck, volume in ((source_deck, source_volume), (target_deck, target_volume)):
            try:
                deck.set_volume(volume)
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "Failed to set volume on deck %r during crossfade", deck
                )

    def _finish_locked(self, cancelled: bool) -> None:
        """Must be called with `self._lock` held."""
        source_deck = self._source_deck
        target_deck = self._target_deck
        self._active = False
        self._thread = None

        if not cancelled and source_deck is not None and target_deck is not None:
            for callback in list(self._on_complete_listeners):
                try:
                    callback(source_deck, target_deck)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("on_complete listener raised an exception")

    # ------------------------------------------------------------------
    # Internal: validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_duration(duration_seconds: float) -> None:
        try:
            value = float(duration_seconds)
        except (TypeError, ValueError) as exc:
            raise InvalidCrossfadeError(
                f"Crossfade duration must be a number, got {duration_seconds!r}."
            ) from exc
        if math.isnan(value) or math.isinf(value):
            raise InvalidCrossfadeError(
                f"Crossfade duration must be a finite number, got {duration_seconds!r}."
            )
        if value < 0.0:
            raise InvalidCrossfadeError(
                f"Crossfade duration must be >= 0, got {value}."
            )
