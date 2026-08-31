from pathlib import Path

from src.decoder import AudioDecoder, DecodedAudio
import numpy as np


def test_preload_is_shared_between_decoder_instances(tmp_path, monkeypatch):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"fake")
    decoded = DecodedAudio(str(audio), np.zeros((8, 2), dtype=np.float32), 44100, 2)
    calls = []

    original = AudioDecoder.decode
    monkeypatch.setattr(AudioDecoder, "decode", lambda self, path: calls.append(path) or decoded)
    AudioDecoder.clear_cache()

    d1 = AudioDecoder()
    d2 = AudioDecoder()
    d1.preload(str(audio))

    import time
    deadline = time.time() + 2
    while time.time() < deadline and not calls:
        time.sleep(0.01)

    assert calls == [str(audio)]
    assert d2.decode_cached(str(audio)) is decoded

    AudioDecoder.clear_cache()
    monkeypatch.setattr(AudioDecoder, "decode", original)
