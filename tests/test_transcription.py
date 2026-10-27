"""Deterministic unit tests for whisper.cpp transcription adapter."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.transcription import (
    TranscriptionError,
    TranscriptSegment,
    transcribe_audio_file,
)


def test_missing_whisper_binary(tmp_path: Path):
    """Test that missing whisper.cpp binary raises TRANSCRIBER_UNAVAILABLE."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")

    with patch("subprocess.run", side_effect=FileNotFoundError("No such file")):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(audio_path, whisper_bin="/nonexistent/whisper-cli")
        assert exc.value.code == "TRANSCRIBER_UNAVAILABLE"


def test_missing_whisper_model(tmp_path: Path):
    """Test that missing GGML model file raises TRANSCRIBER_UNAVAILABLE."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(
                audio_path,
                model_path=tmp_path / "nonexistent_model.bin",
                whisper_bin="/usr/bin/whisper-cli",
            )
        assert exc.value.code == "TRANSCRIBER_UNAVAILABLE"


def test_transcription_timeout(tmp_path: Path):
    """Test that whisper subprocess timeout raises TRANSCRIBER_TIMEOUT."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model_bytes")

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(
                audio_path,
                model_path=model_path,
                whisper_bin="/usr/bin/whisper-cli",
                timeout=5,
            )
        assert exc.value.code == "TRANSCRIBER_TIMEOUT"


def test_transcription_subprocess_failure(tmp_path: Path):
    """Test that whisper-cli exiting with non-zero code raises TRANSCRIBER_FAILED."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model_bytes")

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0)
        return MagicMock(returncode=1, stderr="Failed to load audio", stdout="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(
                audio_path,
                model_path=model_path,
                whisper_bin="/usr/bin/whisper-cli",
            )
        assert exc.value.code == "TRANSCRIBER_FAILED"


def test_malformed_whisper_json_output(tmp_path: Path):
    """Test that malformed JSON from whisper-cli raises INVALID_TRANSCRIPTION_OUTPUT."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model_bytes")

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0)
        # Find output file path from -of
        of_idx = cmd.index("-of")
        of_base = Path(cmd[of_idx + 1])
        json_file = Path(f"{of_base}.json")
        json_file.write_text("{ not valid json content !!!", encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(
                audio_path,
                model_path=model_path,
                whisper_bin="/usr/bin/whisper-cli",
            )
        assert exc.value.code == "INVALID_TRANSCRIPTION_OUTPUT"


def test_non_chronological_segments_rejected(tmp_path: Path):
    """Test that whisper segments with inverted or non-chronological timestamps are rejected."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model_bytes")

    inverted_output = {
        "transcription": [
            {"offsets": {"from": 5000, "to": 8000}, "text": "Later moment"},
            {"offsets": {"from": 2000, "to": 4000}, "text": "Earlier moment"},  # non-chronological!
        ]
    }

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0)
        of_idx = cmd.index("-of")
        of_base = Path(cmd[of_idx + 1])
        json_file = Path(f"{of_base}.json")
        json_file.write_text(json.dumps(inverted_output), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        with pytest.raises(TranscriptionError) as exc:
            transcribe_audio_file(
                audio_path,
                model_path=model_path,
                whisper_bin="/usr/bin/whisper-cli",
            )
        assert exc.value.code == "INVALID_TRANSCRIPTION_OUTPUT"


def test_valid_transcription_parsing(tmp_path: Path):
    """Test that properly formatted whisper-cli JSON segments are cleanly parsed."""
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"dummy")
    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"model_bytes")

    valid_output = {
        "transcription": [
            {"offsets": {"from": 0, "to": 3500}, "text": " First memory segment."},
            {"offsets": {"from": 3500, "to": 7200}, "text": " Second memory segment."},
        ]
    }

    def mock_subprocess_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0)
        of_idx = cmd.index("-of")
        of_base = Path(cmd[of_idx + 1])
        json_file = Path(f"{of_base}.json")
        json_file.write_text(json.dumps(valid_output), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        segments = transcribe_audio_file(
            audio_path,
            model_path=model_path,
            whisper_bin="/usr/bin/whisper-cli",
        )
        assert len(segments) == 2
        assert segments[0].segment_index == 0
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 3500
        assert segments[0].text == "First memory segment."
        assert segments[1].start_ms == 3500
        assert segments[1].end_ms == 7200
        assert segments[1].text == "Second memory segment."
