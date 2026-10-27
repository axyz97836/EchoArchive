"""Deterministic unit tests for media validation, ingestion, and limits."""

import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import MAX_AUDIO_DURATION_SECONDS, MAX_AUDIO_SIZE_BYTES
from backend.media import (
    MediaValidationError,
    probe_audio_duration,
    sanitize_filename,
    validate_audio,
    validate_extension,
    validate_file_size,
)


def create_dummy_wav(path: Path, duration_seconds: float, sample_rate: int = 16000) -> None:
    """Create a minimal valid PCM WAV file for deterministic testing."""
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)


def test_valid_audio_input(tmp_path: Path):
    """Test that a valid audio file within limits passes validation."""
    wav_path = tmp_path / "valid.wav"
    create_dummy_wav(wav_path, duration_seconds=5.0)

    size, duration = validate_audio(wav_path)
    assert size > 0
    assert 4.9 <= duration <= 5.1


def test_unsupported_audio_formats():
    """Test that unsupported file extensions are rejected."""
    with pytest.raises(MediaValidationError) as exc:
        validate_extension("recording.txt")
    assert exc.value.code == "UNSUPPORTED_AUDIO"

    with pytest.raises(MediaValidationError) as exc:
        validate_extension("virus.exe")
    assert exc.value.code == "UNSUPPORTED_AUDIO"

    with pytest.raises(MediaValidationError) as exc:
        validate_extension("movie.mkv")
    assert exc.value.code == "UNSUPPORTED_AUDIO"


def test_audio_exceeding_25_mib(tmp_path: Path):
    """Test that audio exceeding 25 MiB is rejected with AUDIO_TOO_LARGE."""
    large_file = tmp_path / "large.wav"
    large_file.write_bytes(b"0" * 1024)

    # Mock st_size to exceed 25 MiB
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = MAX_AUDIO_SIZE_BYTES + 1024
        with pytest.raises(MediaValidationError) as exc:
            validate_file_size(large_file)
        assert exc.value.code == "AUDIO_TOO_LARGE"


def test_audio_exceeding_five_minutes(tmp_path: Path):
    """Test that audio exceeding 5 minutes (300s) is rejected with AUDIO_TOO_LONG."""
    long_file = tmp_path / "too_long.wav"
    create_dummy_wav(long_file, duration_seconds=1.0)

    with patch("backend.media.probe_audio_duration", return_value=301.5):
        with pytest.raises(MediaValidationError) as exc:
            validate_audio(long_file)
        assert exc.value.code == "AUDIO_TOO_LONG"


def test_corrupted_or_invalid_audio(tmp_path: Path):
    """Test that corrupted non-audio data is rejected with UNSUPPORTED_AUDIO."""
    corrupted_file = tmp_path / "corrupt.wav"
    corrupted_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x00NOT_VALID_AUDIO_BYTES_HERE")

    with patch("backend.media.check_ffmpeg_available", return_value=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Invalid data found when processing input"
            mock_run.return_value.stdout = ""
            with pytest.raises(MediaValidationError) as exc:
                probe_audio_duration(corrupted_file)
            assert exc.value.code == "UNSUPPORTED_AUDIO"


def test_missing_ffmpeg(tmp_path: Path):
    """Test that missing FFmpeg raises FFMPEG_UNAVAILABLE when needed for probing non-wav or fallback."""
    test_file = tmp_path / "test.mp3"
    test_file.write_bytes(b"fake mp3 data")

    with patch("backend.media.check_ffmpeg_available", return_value=False):
        with pytest.raises(MediaValidationError) as exc:
            probe_audio_duration(test_file)
        assert exc.value.code == "FFMPEG_UNAVAILABLE"


def test_path_traversal_detection():
    """Test that filename path traversal attempts are detected and rejected."""
    with pytest.raises(MediaValidationError) as exc:
        sanitize_filename("../../etc/passwd")
    assert exc.value.code == "PATH_TRAVERSAL"

    with pytest.raises(MediaValidationError) as exc:
        sanitize_filename("folder/nested.wav")
    assert exc.value.code == "PATH_TRAVERSAL"

    assert sanitize_filename("safe_recording.wav") == "safe_recording.wav"
