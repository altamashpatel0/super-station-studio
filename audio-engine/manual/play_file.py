"""
manual/play_file.py
====================

Simple manual smoke-test script: loads and plays a real local audio
file through actual audio hardware using the real `AudioEngine`
(SoundDeviceOutput backend, not the test fake).

Usage (from the audio-engine/ directory):

    python manual/play_file.py "C:\\path\\to\\song.mp3"
    python manual/play_file.py /path/to/song.wav
    python manual/play_file.py /path/to/song.mp3 --volume 0.5 --seek 10

This is a developer convenience tool, not an automated test - it
requires a working audio output device and a real file, and prints
live status to the console.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.engine import AudioEngine
from src.models import AudioEngineError, PlayerState


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually play a local audio file.")
    parser.add_argument("file", help="Path to an MP3 or WAV file to play.")
    parser.add_argument(
        "--volume", type=float, default=1.0, help="Initial volume, 0.0-1.0 (default: 1.0)"
    )
    parser.add_argument(
        "--seek", type=float, default=None, help="Seek to this position (seconds) before playing."
    )
    args = parser.parse_args()

    def on_state_change(old_state: PlayerState, new_state: PlayerState) -> None:
        print(f"[state] {old_state.value} -> {new_state.value}")

    def on_track_complete(file_path: str) -> None:
        print(f"[event] Track completed naturally: {file_path}")

    with AudioEngine() as engine:
        engine.on_state_change(on_state_change)
        engine.on_track_complete(on_track_complete)

        print(f"Loading: {args.file}")
        try:
            status = engine.load_track(args.file)
        except AudioEngineError as exc:
            print(f"ERROR loading file: {exc}")
            return 1

        print(f"Loaded. Duration: {status.duration_seconds:.2f}s")

        engine.set_volume(args.volume)
        if args.seek is not None:
            engine.seek(args.seek)

        engine.play()
        print("Playing... (Ctrl+C to stop early)")

        try:
            while engine.is_playing():
                status = engine.get_status()
                print(
                    f"\r{status.position_seconds:6.2f}s / "
                    f"{status.duration_seconds:6.2f}s  vol={status.volume:.2f}   ",
                    end="",
                    flush=True,
                )
                time.sleep(0.25)
        except KeyboardInterrupt:
            print("\nStopping (Ctrl+C)...")
            engine.stop()

        print("\nDone. Final status:", engine.get_status().to_dict())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
