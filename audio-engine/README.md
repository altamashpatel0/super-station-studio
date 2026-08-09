# Super Station Studio — Audio Engine (V0.1: Core Audio Engine)

A standalone, dependency-injectable Python audio playback engine that
loads and plays local MP3/WAV files, built as the foundation for the
Super Station Studio radio automation system.

This module is **framework-agnostic**: it does not import FastAPI,
HTTP, or JSON. It is designed to be wrapped by a FastAPI service in
V0.2/V0.3 without any changes to this code:

```
React UI -> Electron -> FastAPI -> AudioEngine -> Windows Audio Output
```

## Scope of V0.1

This release implements **only** the core audio engine:

- Load and validate local MP3/WAV files
- Play / Pause / Resume / Stop / Seek / Volume control
- Playback status (position, duration, current file, state)
- A player state machine: `IDLE`, `LOADING`, `PLAYING`, `PAUSED`, `STOPPED`, `ERROR`
- Automatic end-of-track detection with an extension point for future
  automatic next-track playback
- Robust error handling — a bad file never crashes the process

Explicitly **out of scope** for V0.1 (future versions): music library,
playlist editor, scheduler, jingles/ads, clock wheel, reports,
streaming, authentication, and the React/Electron/FastAPI layers
themselves.

## Architecture

```
audio-engine/
├── src/
│   ├── __init__.py       # Public package API
│   ├── models.py         # PlayerState, PlaybackStatus, exceptions
│   ├── decoder.py         # File validation + decoding (PyAV/FFmpeg)
│   ├── audio_output.py    # Audio device output (sounddevice/PortAudio)
│   ├── player.py          # State machine + transport controls
│   └── engine.py          # High-level façade (the future FastAPI-facing API)
├── tests/                 # Automated pytest suite (no real audio hardware needed)
├── manual/
│   └── play_file.py       # Manual smoke-test script (uses real audio hardware)
├── requirements.txt
└── README.md
```

**Responsibility separation:**

| Module            | Responsibility                                            |
|--------------------|------------------------------------------------------------|
| `models.py`        | Shared enums/dataclasses/exceptions — the "vocabulary"     |
| `decoder.py`       | File → PCM samples + metadata. No playback state.          |
| `audio_output.py`  | PCM samples → sound card. No file/format knowledge.        |
| `player.py`        | State machine + transport controls. Owns thread-safety.    |
| `engine.py`        | Public façade. What FastAPI will call in V0.2/V0.3.        |

### Why full in-memory decoding?

Radio automation tracks (songs, jingles, ads, station IDs) are short —
seconds to a few minutes. Decoding the whole file into a NumPy buffer
up front makes sample-accurate seeking trivial and reliable, and keeps
the door open for future features (crossfading, looping, waveform
previews) without re-architecting the decode path. If very long-form
content (e.g. hour-long podcasts) is needed later, a streaming decode
mode can be added as an alternate code path in `decoder.py` without
changing the `Player`/`AudioEngine` public API.

### Why `sounddevice` and not `pygame`?

`sounddevice` binds directly to PortAudio, which has mature WASAPI/
DirectSound support on Windows and is built for exactly this kind of
low-level, callback-driven, professional audio streaming — not a game
library repurposed for audio. `player.py` and `engine.py` never import
`sounddevice` directly; they depend on the `AudioOutputBase` interface
in `audio_output.py`, so the backend can be swapped later (e.g. for
WASAPI exclusive mode or ASIO) without touching playback logic.

### Automatic end detection & future auto-advance

When a track finishes playing naturally, `Player` fires a
`TrackEndReason.COMPLETED` event (distinct from a manual `stop()`,
which fires `MANUAL_STOP`). `AudioEngine.on_track_complete(callback)`
exposes this specifically for natural completions — this is the
intended hook for V0.2's scheduler to load and play the next track
without any changes to this engine.

## Installation

From the `audio-engine/` directory:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

> PyAV ships its own bundled FFmpeg binaries, so no separate system
> FFmpeg install is required on Windows.

## Using the engine

```python
from src.engine import AudioEngine

with AudioEngine() as engine:
    engine.load_track("C:/music/track1.mp3")
    engine.set_volume(0.8)
    engine.play()

    status = engine.get_status()
    print(status.to_dict())

    engine.pause()
    engine.resume()
    engine.seek(30.0)
    engine.stop()
```

Register for events (used by the future scheduler):

```python
engine.on_track_complete(lambda file_path: print(f"{file_path} finished, load next track"))
engine.on_state_change(lambda old, new: print(f"{old} -> {new}"))
```

## Running the manual test script

Requires a real audio output device and a real file:

```bash
python manual/play_file.py "C:\music\song.mp3"
python manual/play_file.py /home/user/music/song.wav --volume 0.5 --seek 10
```

Prints live position/state to the console; `Ctrl+C` stops playback
early.

## Running the automated tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

The automated suite uses a `FakeAudioOutput` test double (see
`tests/fake_audio_output.py`) instead of real hardware, so it runs
reliably in CI/headless environments while still exercising the real
`AudioDecoder` against real, on-the-fly-generated WAV and MP3 files.

Covered by the suite:

- Valid file loading (WAV and MP3)
- Invalid/corrupt file handling
- Missing file handling
- Unsupported format handling
- Full state machine transitions (`IDLE → LOADING → STOPPED → PLAYING → PAUSED → ...`)
- Play / Pause / Resume / Stop
- Seek validation (in-range, out-of-range, negative)
- Volume validation (0.0–1.0 boundaries and out-of-range)
- Duration/status retrieval
- Automatic end-of-track detection and event firing
- Output-device failure handling (never crashes the process)

With coverage:

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

## V0.1 Completion Checklist

- [x] Load local MP3 files
- [x] Load local WAV files
- [x] Validate file existence before decode
- [x] Handle invalid/corrupt files without crashing
- [x] Play / Pause / Resume / Stop / Seek / Volume control
- [x] Expose current position, duration, current file, current state
- [x] Player states: IDLE, LOADING, PLAYING, PAUSED, STOPPED, ERROR
- [x] Automatic end-of-track detection with a completion event
- [x] Extension point ready for automatic next-track playback (V0.2)
- [x] Errors never crash the process (missing file, bad format, decode
      failure, output failure all raise typed exceptions and land in
      `ERROR` state)
- [x] Clean separation: `decoder.py` / `audio_output.py` / `player.py`
      / `engine.py` / `models.py`
- [x] No `pygame` used as the core audio engine
- [x] Automated tests for all required scenarios (50 tests, all passing)
- [x] Manual test script for real-hardware playback
- [x] No hardcoded absolute Windows paths, no secrets
- [x] Type hints and docstrings throughout
- [x] Designed so FastAPI (V0.2) can wrap `AudioEngine` directly, with
      no rewrite of this module

**V0.1 is complete and verified working.** Do not begin V0.2 (FastAPI
integration, playlist/scheduler work) until this module has been
reviewed and accepted.
