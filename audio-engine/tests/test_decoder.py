"""Tests for `src.decoder.AudioDecoder`."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.decoder import AudioDecoder, DecodedAudio
from src.models import (
    AudioFileNotFoundError,
    DecodeError,
    UnsupportedFormatError,
)


class TestValidateFile:
    def test_valid_wav_passes_validation(self, decoder: AudioDecoder, valid_wav_file: Path):
        decoder.validate_file(str(valid_wav_file))  # should not raise

    def test_missing_file_raises(self, decoder: AudioDecoder, missing_file_path: Path):
        with pytest.raises(AudioFileNotFoundError):
            decoder.validate_file(str(missing_file_path))

    def test_empty_path_raises(self, decoder: AudioDecoder):
        with pytest.raises(AudioFileNotFoundError):
            decoder.validate_file("")

    def test_unsupported_extension_raises(
        self, decoder: AudioDecoder, unsupported_format_file: Path
    ):
        with pytest.raises(UnsupportedFormatError):
            decoder.validate_file(str(unsupported_format_file))


class TestDecode:
    def test_valid_wav_decodes_successfully(self, decoder: AudioDecoder, valid_wav_file: Path):
        result = decoder.decode(str(valid_wav_file))

        assert isinstance(result, DecodedAudio)
        assert result.sample_rate > 0
        assert result.channels >= 1
        assert result.total_frames > 0
        assert result.duration_seconds == pytest.approx(0.5, abs=0.05)

    def test_valid_mp3_decodes_successfully(self, decoder: AudioDecoder, valid_mp3_file: Path):
        result = decoder.decode(str(valid_mp3_file))

        assert isinstance(result, DecodedAudio)
        assert result.sample_rate > 0
        assert result.channels >= 1
        assert result.total_frames > 0
        # MP3 encoders commonly add a small amount of priming/padding,
        # so allow a slightly wider tolerance than the WAV case.
        assert result.duration_seconds == pytest.approx(0.5, abs=0.2)

    def test_missing_file_raises(self, decoder: AudioDecoder, missing_file_path: Path):
        with pytest.raises(AudioFileNotFoundError):
            decoder.decode(str(missing_file_path))

    def test_corrupt_file_raises_decode_error(
        self, decoder: AudioDecoder, corrupt_mp3_file: Path
    ):
        with pytest.raises(DecodeError):
            decoder.decode(str(corrupt_mp3_file))

    def test_unsupported_extension_raises(
        self, decoder: AudioDecoder, unsupported_format_file: Path
    ):
        with pytest.raises(UnsupportedFormatError):
            decoder.decode(str(unsupported_format_file))

    def test_decoding_never_raises_generic_exception_for_corrupt_file(
        self, decoder: AudioDecoder, corrupt_mp3_file: Path
    ):
        """Corrupt input must always surface as an AudioEngineError
        subtype, never an unhandled/generic exception that could crash
        the host application."""
        from src.models import AudioEngineError

        try:
            decoder.decode(str(corrupt_mp3_file))
            pytest.fail("Expected an exception to be raised")
        except AudioEngineError:
            pass  # expected


class TestSupportedExtensions:
    def test_mp3_and_wav_supported(self, decoder: AudioDecoder):
        extensions = set(decoder.supported_extensions())
        assert ".mp3" in extensions
        assert ".wav" in extensions
