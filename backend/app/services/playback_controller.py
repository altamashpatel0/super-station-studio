from __future__ import annotations

import enum
import logging
import threading
from collections import defaultdict
from typing import Callable, Optional

from src.engine import AudioEngine
from src.deck import DeckID, TwoDeckEngine
from src.crossfade import CrossfadeController, CrossfadeError, DEFAULT_CROSSFADE_DURATION_SECONDS
from src.models import AudioEngineError, PlaybackStatus, TrackEndReason

logger = logging.getLogger(__name__)

class PlaybackSource(str, enum.Enum):
    MANUAL = "MANUAL"
    QUEUE = "QUEUE"
    SCHEDULE = "SCHEDULE"
    ASSET = "ASSET"

PlaybackCallback = Callable[[TrackEndReason], None]
PreemptCallback = Callable[[PlaybackSource, PlaybackSource], None]
CrossfadeCompleteCallback = Callable[[str, str], None]

class PlaybackControllerError(Exception):
    """Base error for centralized playback failures."""

class PlaybackController:
    """Single playback authority backed by a real two-deck engine.

    The controller keeps the old AudioEngine-like surface for callers while
    making TwoDeckEngine + CrossfadeController the production playback path.
    Content selection remains outside this class.
    """
    def __init__(
        self,
        engine: AudioEngine | TwoDeckEngine,
        *,
        crossfade_duration_seconds: float = DEFAULT_CROSSFADE_DURATION_SECONDS,
        use_two_deck: bool = False,
    ) -> None:
        self._legacy_engine: Optional[AudioEngine] = None if use_two_deck else (engine if isinstance(engine, AudioEngine) else None)
        self._two_deck_mode = bool(use_two_deck or isinstance(engine, TwoDeckEngine))
        self._two_deck: TwoDeckEngine = (
            engine if isinstance(engine, TwoDeckEngine)
            else TwoDeckEngine() if self._two_deck_mode
            else TwoDeckEngine()
        )
        self._lock = threading.RLock()
        self._active_source: Optional[PlaybackSource] = None
        self._generation = 0
        self._active_deck_id = DeckID.A
        self._crossfade = CrossfadeController(duration_seconds=crossfade_duration_seconds)
        self._next_file_path: Optional[str] = None
        self._crossfade_started_generation: Optional[int] = None
        self._transition_callback: Optional[CrossfadeCompleteCallback] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._completion_handlers: dict[PlaybackSource, list[PlaybackCallback]] = defaultdict(list)
        self._preempt_handlers: dict[PlaybackSource, list[PreemptCallback]] = defaultdict(list)
        self._crossfade.on_complete(self._on_crossfade_complete)

        for deck_id in (DeckID.A, DeckID.B):
            self._two_deck.get_deck(deck_id).on_track_end(
                lambda reason, deck_id=deck_id: self._on_deck_track_end(deck_id, reason)
            )

        # Preserve the exact legacy fake-engine behavior used by existing tests.
        if self._legacy_engine is not None:
            self._legacy_engine.on_track_end(self._on_legacy_track_end)

    @property
    def engine(self) -> AudioEngine:
        """Return the currently active deck using the legacy AudioEngine API."""
        if self._legacy_engine is not None:
            return self._legacy_engine
        return self._two_deck.get_deck(self._active_deck_id)

    @property
    def two_deck_engine(self) -> TwoDeckEngine:
        return self._two_deck

    @property
    def crossfade_controller(self) -> CrossfadeController:
        return self._crossfade

    @property
    def active_source(self) -> Optional[PlaybackSource]:
        with self._lock:
            return self._active_source

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def active_deck_id(self) -> DeckID:
        with self._lock:
            return self._active_deck_id

    def register_completion_handler(self, source: PlaybackSource, callback: PlaybackCallback) -> None:
        with self._lock:
            if callback not in self._completion_handlers[source]:
                self._completion_handlers[source].append(callback)

    def register_preempt_handler(self, source: PlaybackSource, callback: PreemptCallback) -> None:
        with self._lock:
            if callback not in self._preempt_handlers[source]:
                self._preempt_handlers[source].append(callback)

    def owns(self, source: PlaybackSource) -> bool:
        with self._lock:
            return self._active_source == source

    def start_track(
        self,
        source: PlaybackSource,
        file_path: str,
        *,
        next_file_path: Optional[str] = None,
        on_crossfade_complete: Optional[CrossfadeCompleteCallback] = None,
    ) -> PlaybackStatus:
        return self.start(
            source,
            lambda: self._load_and_play(file_path),
            next_file_path=next_file_path,
            on_crossfade_complete=on_crossfade_complete,
        )

    def start(
        self,
        source: PlaybackSource,
        starter: Callable[[], object],
        *,
        next_file_path: Optional[str] = None,
        on_crossfade_complete: Optional[CrossfadeCompleteCallback] = None,
    ):
        with self._lock:
            previous = self._active_source
            if previous is not None and previous != source:
                # Station playout follows a strict "last valid request wins"
                # rule. Manual, queue, asset and scheduled playback may all
                # replace the currently active source. Notify subscribers
                # first so they can persist the previous item as SKIPPED and
                # clear source-specific runtime state, then stop the current
                # deck before loading the replacement.
                self._notify_preempt(previous, source)
                self._cancel_crossfade_locked()
                try:
                    self.engine.stop()
                except Exception:
                    # The engine may already be STOPPED/ERROR after a rapid
                    # transition. The new request should still be allowed to
                    # attempt playback; its starter below will surface a real
                    # load/play failure if one exists.
                    logger.debug("Previous playback was already stopped during source replacement.", exc_info=True)

            self._generation += 1
            self._active_source = source
            self._next_file_path = next_file_path
            self._transition_callback = on_crossfade_complete
            self._crossfade_started_generation = None
            generation = self._generation

            try:
                result = starter()
            except Exception:
                if self._generation == generation:
                    self._active_source = previous
                    self._next_file_path = None
                    self._transition_callback = None
                raise

            if next_file_path and self._two_deck_mode:
                self._start_monitor_locked()
            else:
                self._stop_monitor_locked()
            return result

    def set_next_track(
        self,
        file_path: Optional[str],
        on_crossfade_complete: Optional[CrossfadeCompleteCallback] = None,
    ) -> None:
        with self._lock:
            self._next_file_path = file_path
            if on_crossfade_complete is not None:
                self._transition_callback = on_crossfade_complete
            self._crossfade_started_generation = None
            if file_path:
                self._start_monitor_locked()

    def preload_track(self, file_path: Optional[str]) -> None:
        """Best-effort background decode of a future track."""
        if not file_path:
            return
        with self._lock:
            engine = self.engine
            try:
                engine.preload_track(file_path)
            except Exception:
                logger.debug("Queue next-track preload failed for %s", file_path, exc_info=True)

    def pause(self) -> PlaybackStatus:
        """Pause the currently active playback without changing its owner."""
        with self._lock:
            return self.engine.pause()

    def resume(self) -> PlaybackStatus:
        """Resume the currently active playback without changing its owner."""
        with self._lock:
            return self.engine.resume()

    def stop(self, source: Optional[PlaybackSource] = None) -> PlaybackStatus:
        with self._lock:
            if source is not None and source != PlaybackSource.MANUAL and self._active_source != source:
                raise PlaybackControllerError(
                    f"{source.value} cannot stop playback owned by {self._active_source.value if self._active_source else 'NONE'}."
                )
            self._cancel_crossfade_locked()
            self._stop_monitor_locked()
            result = self.engine.stop()
            self._active_source = None
            self._next_file_path = None
            self._transition_callback = None
            self._generation += 1
            return result

    def release_if_owned(self, source: PlaybackSource) -> None:
        with self._lock:
            if self._active_source == source:
                self._active_source = None
                self._next_file_path = None
                self._transition_callback = None
                self._generation += 1

    def get_status(self) -> dict:
        status = self.engine.get_status()
        data = status.to_dict()
        with self._lock:
            data.update({
                "playback_source": self._active_source.value if self._active_source else None,
                "playback_generation": self._generation,
                "active_deck": self._active_deck_id.value,
                "crossfading": self._crossfade.is_active(),
                "crossfade_progress": self._crossfade.progress(),
                "crossfade_remaining_seconds": self._crossfade.remaining_time(),
                "crossfade_source_deck": self._crossfade.source_deck.deck_id.value if self._crossfade.source_deck else None,
                "crossfade_target_deck": self._crossfade.target_deck.deck_id.value if self._crossfade.target_deck else None,
                "next_file_path": self._next_file_path,
            })
        return data

    def shutdown(self) -> None:
        with self._lock:
            self._cancel_crossfade_locked()
            self._stop_monitor_locked()
            self._active_source = None
        if self._two_deck_mode:
            self._two_deck.shutdown()
        if self._legacy_engine is not None:
            try:
                self._legacy_engine.shutdown()
            except Exception:
                logger.debug("Legacy engine shutdown failed", exc_info=True)

    def _load_and_play(self, file_path: str) -> PlaybackStatus:
        if self._legacy_engine is not None:
            self._legacy_engine.load_track(file_path)
            return self._legacy_engine.play()
        deck = self._two_deck.get_deck(self._active_deck_id)
        deck.load_track(file_path)
        deck.set_volume(1.0)
        return deck.play()

    def _start_monitor_locked(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop = threading.Event()
        thread = threading.Thread(
            target=self._monitor_loop, args=(self._monitor_stop,),
            name="PlaybackCrossfadeMonitor", daemon=True,
        )
        self._monitor_thread = thread
        thread.start()

    def _stop_monitor_locked(self) -> None:
        event = self._monitor_stop
        event.set()
        self._monitor_thread = None

    def _monitor_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(0.1):
            try:
                self._poll_crossfade()
            except Exception:
                logger.exception("Playback crossfade monitor failed")

    def _poll_crossfade(self) -> None:
        with self._lock:
            if not self._two_deck_mode or not self._next_file_path or self._crossfade.is_active():
                return
            if self._crossfade_started_generation == self._generation:
                return
            deck = self._two_deck.get_deck(self._active_deck_id)
            status = deck.get_status()
            if status.state.name != "PLAYING":
                return
            remaining = max(status.duration_seconds - status.position_seconds, 0.0)
            duration = min(self._crossfade.default_duration, remaining)
            if remaining > self._crossfade.default_duration:
                return
            target_id = DeckID.B if self._active_deck_id == DeckID.A else DeckID.A
            target = self._two_deck.get_deck(target_id)
            next_path = self._next_file_path
            generation = self._generation
            try:
                target.load_track(next_path)
                target.set_volume(0.0)
                self._crossfade.start(deck, target, duration_seconds=duration)
                self._crossfade_started_generation = generation
            except (AudioEngineError, CrossfadeError):
                logger.exception("Failed to prepare/start crossfade into %s", next_path)
                try:
                    target.stop()
                except Exception:
                    pass

    def _on_crossfade_complete(self, source_deck, target_deck) -> None:
        callback = None
        old_path = source_deck.get_status().file_path
        new_path = target_deck.get_status().file_path
        with self._lock:
            self._active_deck_id = target_deck.deck_id
            self._generation += 1
            self._crossfade_started_generation = None
            callback = self._transition_callback
            self._next_file_path = None
            self._transition_callback = None
        # Do not stop the source deck synchronously from the crossfade
        # completion callback. sounddevice/PortAudio can still be executing
        # the output callback on this thread. Defer the stop to a worker so
        # the native callback is allowed to return first.
        threading.Thread(
            target=self._safe_stop_deck,
            args=(source_deck,),
            name="PlaybackDeferredDeckStop",
            daemon=True,
        ).start()
        if callback and old_path and new_path:
            try:
                callback(old_path, new_path)
            except Exception:
                logger.exception("Crossfade completion callback failed")

    @staticmethod
    def _safe_stop_deck(deck) -> None:
        """Stop a completed source deck outside the PortAudio callback thread."""
        try:
            deck.stop()
        except Exception:
            logger.debug("Deferred source deck stop failed", exc_info=True)

    def _on_deck_track_end(self, deck_id: DeckID, reason: TrackEndReason) -> None:
        with self._lock:
            if deck_id != self._active_deck_id:
                return
            if reason == TrackEndReason.COMPLETED and self._crossfade.is_active():
                return
            source = self._active_source
            callbacks = list(self._completion_handlers.get(source, ())) if source else []
            if reason != TrackEndReason.COMPLETED:
                self._active_source = None
                self._next_file_path = None
                self._transition_callback = None
                self._stop_monitor_locked()
        for callback in callbacks:
            try:
                callback(reason)
            except Exception:
                logger.exception("Playback completion handler failed for %s", source.value if source else "NONE")

    def _on_legacy_track_end(self, reason: TrackEndReason) -> None:
        # Compatibility only. Production playback uses the two-deck callbacks.
        if self._legacy_engine is None:
            return
        self._on_deck_track_end(self._active_deck_id, reason)

    def _notify_preempt(self, previous: PlaybackSource, new: PlaybackSource) -> None:
        for callback in list(self._preempt_handlers.get(previous, ())):
            try:
                callback(previous, new)
            except Exception:
                logger.exception("Playback preemption handler failed: %s -> %s", previous.value, new.value)

    def _cancel_crossfade_locked(self) -> None:
        self._crossfade.cancel()
        self._crossfade_started_generation = None
