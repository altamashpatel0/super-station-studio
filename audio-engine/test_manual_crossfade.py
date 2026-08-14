"""
test_manual_crossfade.py
=========================

TEMPORARY manual smoke test for the V0.4 `TwoDeckEngine` +
`CrossfadeController`, meant to be run by hand (not by pytest) with
real speakers so you can actually *hear* the crossfade.

This script only uses the existing, public V0.4 APIs:
    - src.deck.TwoDeckEngine
    - src.crossfade.CrossfadeController

It does not modify, monkeypatch, or reimplement anything in `src/`.

Usage:
    python test_manual_crossfade.py

You will be prompted for two audio file paths (MP3 or WAV), Deck A
will start playing song 1, and once you press Enter, a 5-second
crossfade into Deck B (song 2) will begin.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running this script directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.deck import TwoDeckEngine
from src.crossfade import CrossfadeController, CrossfadeError

CROSSFADE_DURATION_SECONDS = 5.0
PROGRESS_POLL_INTERVAL_SECONDS = 0.5


def prompt_for_path(label: str) -> str:
    while True:
        raw_path = input(f"Enter path to {label} (MP3/WAV): ").strip().strip('"')
        path = Path(raw_path)
        if path.is_file():
            return str(path)
        print(f"  '{raw_path}' does not exist or is not a file. Try again.")


def main() -> None:
    print("=== V0.4 Manual Crossfade Test ===\n")

    # 1. Ask for two file paths.
    song_1_path = prompt_for_path("Song 1 (Deck A)")
    song_2_path = prompt_for_path("Song 2 (Deck B)")

    # 2. Create TwoDeckEngine (real audio output devices - default ctor).
    two_deck_engine = TwoDeckEngine()

    try:
        deck_a = two_deck_engine.deck_a
        deck_b = two_deck_engine.deck_b

        # 3 & 4. Load song 1 into Deck A, song 2 into Deck B.
        print(f"\nLoading Deck A: {song_1_path}")
        deck_a.load_track(song_1_path)

        print(f"Loading Deck B: {song_2_path}")
        deck_b.load_track(song_2_path)

        # 5 & 6. Set initial volumes.
        deck_a.set_volume(1.0)
        deck_b.set_volume(0.0)

        # 7. Play Deck A.
        print("\nPlaying Deck A...")
        deck_a.play()

        # 8. Wait for the user.
        input("\nDeck A is playing. Press Enter to start the crossfade to Deck B...")

        # 9. Start Deck B and the crossfade.
        print(f"\nStarting Deck B and a {CROSSFADE_DURATION_SECONDS:.1f}s crossfade...")
        deck_b.play()

        controller = CrossfadeController(duration_seconds=CROSSFADE_DURATION_SECONDS)
        try:
            controller.start(deck_a, deck_b)
        except CrossfadeError as exc:
            print(f"Crossfade failed to start: {exc}")
            return

        # 10. Print progress every 0.5 seconds until it completes.
        while controller.is_active():
            pct = controller.progress() * 100.0
            remaining = controller.remaining_time()
            print(
                f"  crossfade progress: {pct:5.1f}%  "
                f"(A vol={deck_a.get_volume():.2f}, B vol={deck_b.get_volume():.2f}, "
                f"remaining={remaining:4.1f}s)"
            )
            time.sleep(PROGRESS_POLL_INTERVAL_SECONDS)

        # 11. Verify final volumes.
        print(f"\nCrossfade complete. progress={controller.progress() * 100.0:.1f}%")
        print(f"  Deck A volume: {deck_a.get_volume():.3f} (expected ~0.0)")
        print(f"  Deck B volume: {deck_b.get_volume():.3f} (expected ~1.0)")

    finally:
        # 12. Cleanly shut down both decks no matter what happened above.
        print("\nShutting down decks...")
        two_deck_engine.shutdown()
        print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
