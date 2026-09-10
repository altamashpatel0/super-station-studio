from pathlib import Path

from src.audio_output import AudioOutputBase
from src.decoder import AudioDecoder, DecodedAudio
from src.engine import AudioEngine


class FakeOutput(AudioOutputBase):
    def __init__(self):
        self.started = False
        self.opens = 0

    def open(self, sample_rate, channels):
        self.opens += 1

    def start(self, read_callback, on_finished):
        self.started = True

    def pause(self):
        self.started = False

    def resume(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.started = False

    @property
    def is_active(self):
        return self.started


class CountingDecoder(AudioDecoder):
    def __init__(self):
        self.calls = []

    def decode(self, file_path):
        self.calls.append(file_path)
        return DecodedAudio(
            file_path=file_path,
            samples=__import__('numpy').zeros((100, 2), dtype='float32'),
            sample_rate=44100,
            channels=2,
        )


def test_preload_is_reused_without_second_decode(tmp_path: Path):
    decoder = CountingDecoder()
    engine = AudioEngine(audio_output=FakeOutput(), decoder=decoder)
    try:
        path = str(tmp_path / 'next.mp3')
        engine.preload_track(path)
        # Force completion through the public load path; it must consume the
        # warmed decode instead of invoking decoder.decode again.
        engine.load_track(path)
        assert decoder.calls == [path]
    finally:
        engine.shutdown()
