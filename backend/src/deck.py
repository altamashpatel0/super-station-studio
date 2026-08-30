"""
deck.py
=======

V0.4 foundation: two independent playback "decks" (A and B), each of
which is a fully independent audio channel - own decode state, own
transport state machine, own audio output device, own volume.

Design intent
--------------
Nothing about V0.1's `AudioEngine` was single-instance by accident: it
already takes its `Player` and `AudioOutputBase` as constructor
arguments and holds no module-level/global state. That means two
`AudioEngine` instances are *already* completely independent of one
another - V0.4 does not need to duplicate or rewrite any decode,
transport, or output logic to get two decks. It only needs a thin
layer that:

    1. Gives each independent `AudioEngine` instance a stable identity
       (`DeckID.A` / `DeckID.B`) - `Deck`.
    2. Owns exactly one of each deck and hands them out by ID -
       `TwoDeckEngine`.

`Deck` is deliberately just `AudioEngine` plus an identifier - not a
reimplementation - so every existing V0.1 behaviour (states, errors,
events, status snapshots) is inherited unchanged and only has to be
tested once (in `test_engine.py` / `test_player.py`). This also means
the existing single-deck `AudioEngine` API keeps working exactly as
before for any V0.2/V0.3 code that already depends on it directly;
`TwoDeckEngine` is purely additive.

Forward-looking hook for crossfading
-------------------------------------
A future `CrossfadeController` needs to be able to:
    - grab both decks independently (`TwoDeckEngine.get_deck`, or the
      `.deck_a` / `.deck_b` attributes directly)
    - ramp each deck's volume over time without the decks knowing or
      caring about each other

Both are already possible with what's here: `Deck.set_volume()` /
`Deck.get_volume()` (inherited from `AudioEngine`) are the exact knobs
a crossfade ramp would call on a timer, and because each deck has its
own `Player`/`AudioOutputBase`, driving deck A's volume down while
driving deck B's volume up cannot cross-contaminate state. No changes
to this module should be required to build that controller later - it
would live in its own `crossfade.py` and simply hold references to
`deck_a` and `deck_b`.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Optional

from .audio_output import AudioOutputBase
from .decoder import AudioDecoder
from .engine import AudioEngine

logger = logging.getLogger(__name__)


class DeckID(str, Enum):
    """Stable identifier for one of the two playback channels."""

    A = "A"
    B = "B"


class Deck(AudioEngine):
    """
    A single independent playback channel.

    `Deck` adds no new playback behaviour on top of `AudioEngine` - it
    *is* an `AudioEngine`, with the exact same load/play/pause/resume/
    stop/seek/volume/status API and the exact same event hooks
    (`on_track_complete`, `on_state_change`, `on_track_end`). The only
    addition is `deck_id`, so a caller (or a future
    `CrossfadeController`) can tell decks apart without needing to
    track object identity itself.
    """

    def __init__(
        self,
        deck_id: DeckID,
        audio_output: Optional[AudioOutputBase] = None,
        decoder: Optional[AudioDecoder] = None,
    ) -> None:
        super().__init__(audio_output=audio_output, decoder=decoder)
        self.deck_id = deck_id

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        status = self.get_status()
        return (
            f"<Deck {self.deck_id.value}: {status.state.value} "
            f"file={status.file_path!r}>"
        )


class TwoDeckEngine:
    """
    Owns two fully independent `Deck` instances: `deck_a` and `deck_b`.

    Each deck gets its own `AudioOutputBase` (defaulting to a separate
    real `SoundDeviceOutput` per deck, exactly as `AudioEngine` already
    does for a single instance) and its own `AudioDecoder`. Nothing is
    shared between decks, so operations on one (load/play/pause/
    resume/stop/seek/volume) can never affect the other's state.

    This class intentionally does *not* implement crossfading,
    scheduling, or playlist logic - it is only the V0.4 foundation
    that a `CrossfadeController` and the existing V0.3 playlist/queue
    layer can be built on top of later.
    """

    def __init__(
        self,
        deck_a_output: Optional[AudioOutputBase] = None,
        deck_b_output: Optional[AudioOutputBase] = None,
        deck_a_decoder: Optional[AudioDecoder] = None,
        deck_b_decoder: Optional[AudioDecoder] = None,
    ) -> None:
        self.deck_a = Deck(
            DeckID.A,
            audio_output=deck_a_output,
            decoder=deck_a_decoder,
        )
        self.deck_b = Deck(
            DeckID.B,
            audio_output=deck_b_output,
            decoder=deck_b_decoder,
        )
        self._decks: Dict[DeckID, Deck] = {
            DeckID.A: self.deck_a,
            DeckID.B: self.deck_b,
        }

    def get_deck(self, deck_id: DeckID) -> Deck:
        """Return the `Deck` for the given `DeckID`."""
        return self._decks[deck_id]

    @property
    def decks(self) -> Dict[DeckID, Deck]:
        """Read-only-by-convention view of both decks, keyed by ID."""
        return dict(self._decks)

    def shutdown(self) -> None:
        """Release both decks' audio output devices."""
        for deck_id, deck in self._decks.items():
            try:
                deck.shutdown()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error shutting down deck %s", deck_id.value)

    def __enter__(self) -> "TwoDeckEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
