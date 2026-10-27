"""Audio ingestion, validation, and FFmpeg preprocessing for EchoArchive."""

import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Dict, Optional, Tuple

from backend.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    FFMPEG_BIN_PATH,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    MEDIA_DIR,
)


class MediaValidationError(Exception):
    """Exception raised when media input violates validation constraints."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_file_size(file_path: Path) -> int:
    """Validate that the file size is within the allowed bounds."""
    if not file_path.exists():
        raise MediaValidationError("UNSUPPORTED_AUDIO", "Audio file does not exist.")
    size = file_path.stat().st_size
    if size <= 0:
        raise MediaValidationError("UNSUPPORTED_AUDIO", "Audio file is empty.")
    if size > MAX_AUDIO_SIZE_BYTES:
        raise MediaValidationError(
            "AUDIO_TOO_LARGE",
            f"Audio file size ({size / (1024 * 1024):.1f} MiB) exceeds maximum limit of 25 MiB."
        )
    return size


def validate_extension(filename: str) -> str:
    """Validate and return normalized lowercase extension."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise MediaValidationError(
            "UNSUPPORTED_AUDIO",
            f"Unsupported audio format '{suffix}'. Allowed formats: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}."
        )
    return suffix


def sanitize_filename(filename: str) -> str:
    """Check for path traversal attempts and return base filename."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise MediaValidationError("PATH_TRAVERSAL", "Path traversal in filename is prohibited.")
    return Path(filename).name


def check_ffmpeg_available() -> bool:
    """Check if the local FFmpeg binary is executable."""
    try:
        proc = subprocess.run(
            [FFMPEG_BIN_PATH, "-version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def probe_audio_duration(file_path: Path) -> float:
    """
    Probe the audio duration in seconds.
    Uses Python's native wave module for WAV files if valid, or FFmpeg output inspection.
    """
    # Try native wave module first for WAV files
    if file_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(file_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0 and frames > 0:
                    duration = frames / float(rate)
                    return duration
        except (wave.Error, EOFError):
            pass

    # Fall back to FFmpeg probe
    if not check_ffmpeg_available():
        raise MediaValidationError(
            "FFMPEG_UNAVAILABLE",
            "Local FFmpeg binary is unavailable for audio validation."
        )

    try:
        proc = subprocess.run(
            [FFMPEG_BIN_PATH, "-i", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = proc.stderr or proc.stdout or ""
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        if match:
            hours, minutes, seconds = match.groups()
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            return duration

        # If FFmpeg reports invalid data or decoding failure
        if "Invalid data found" in output or "could not find codec parameters" in output:
            raise MediaValidationError(
                "UNSUPPORTED_AUDIO",
                "Audio file contains invalid or corrupted data and could not be decoded."
            )

        raise MediaValidationError(
            "UNSUPPORTED_AUDIO",
            "Unable to parse duration from audio stream."
        )
    except subprocess.TimeoutExpired:
        raise MediaValidationError("UNSUPPORTED_AUDIO", "Audio probe timed out.")
    except MediaValidationError:
        raise
    except Exception as e:
        raise MediaValidationError("UNSUPPORTED_AUDIO", f"Failed to probe audio: {str(e)}")


def validate_audio(file_path: Path) -> Tuple[int, float]:
    """
    Run full validation on an audio file: size, extension, and duration limits.
    Returns (size_bytes, duration_seconds).
    """
    size_bytes = validate_file_size(file_path)
    validate_extension(file_path.name)
    duration_seconds = probe_audio_duration(file_path)

    if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
        raise MediaValidationError(
            "AUDIO_TOO_LONG",
            f"Audio duration ({duration_seconds:.1f}s) exceeds maximum limit of {MAX_AUDIO_DURATION_SECONDS}s."
        )

    return size_bytes, duration_seconds


def normalize_to_whisper_wav(input_path: Path, output_wav_path: Path) -> None:
    """
    Safely convert any supported audio file to 16 kHz mono 16-bit PCM WAV for whisper.cpp.
    Uses explicit argument array with no shell injection.
    """
    if not check_ffmpeg_available():
        raise MediaValidationError(
            "FFMPEG_UNAVAILABLE",
            "Local FFmpeg is required to normalize audio for speech recognition."
        )

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN_PATH,
        "-y",
        "-i", str(input_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_wav_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise MediaValidationError(
                "UNSUPPORTED_AUDIO",
                f"Audio conversion failed: {proc.stderr[:200] if proc.stderr else 'Unknown error'}"
            )
    except subprocess.TimeoutExpired:
        raise MediaValidationError("UNSUPPORTED_AUDIO", "Audio normalization timed out.")
    except Exception as e:
        raise MediaValidationError("UNSUPPORTED_AUDIO", f"Audio normalization failed: {str(e)}")
