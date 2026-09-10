from __future__ import annotations

from app.services.playback_controller import PlaybackController, PlaybackSource
from src.engine import AudioEngine
from tests.fakes import FakeAudioOutput, FakeDecoder


def _engine_and_controller():
    decoder = FakeDecoder()
    output = FakeAudioOutput()
    engine = AudioEngine(audio_output=output, decoder=decoder)
    return engine, decoder, output, PlaybackController(engine)


def test_completed_schedule_releases_stale_controller_ownership(tmp_path):
    path = str(tmp_path / "scheduled.wav")
    open(path, "wb").write(b"x")
    engine, decoder, output, controller = _engine_and_controller()
    decoder.register(path)
    try:
        controller.start_track(PlaybackSource.SCHEDULE, path)
        output.simulate_completion()
        assert controller.active_source is None
    finally:
        controller.shutdown()


def test_forced_queue_start_can_override_schedule(tmp_path):
    scheduled = str(tmp_path / "scheduled.wav")
    queued = str(tmp_path / "queued.wav")
    for path in (scheduled, queued):
        open(path, "wb").write(b"x")
    engine, decoder, output, controller = _engine_and_controller()
    decoder.register(scheduled)
    decoder.register(queued)
    try:
        controller.start_track(PlaybackSource.SCHEDULE, scheduled)
        controller.start_track(PlaybackSource.QUEUE, queued, force=True)
        assert controller.active_source == PlaybackSource.QUEUE
        assert engine.get_status().file_path == queued
    finally:
        controller.shutdown()
