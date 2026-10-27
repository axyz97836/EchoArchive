"""Audio ingestion, validation, and FFmpeg preprocessing for EchoArchive."""

import os
import re
import shutil
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import UploadFile

from backend.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    FFMPEG_BIN_PATH,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    MEDIA_DIR,
    TMP_DIR,
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
    if not filename or not filename.strip():
        raise MediaValidationError("UNSUPPORTED_AUDIO", "Filename is required.")
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
            # If the file claimed to be WAV but lacks a valid RIFF/WAVE header, it is corrupted/unsupported
            try:
                with open(file_path, "rb") as f:
                    hdr = f.read(12)
                if not hdr.startswith(b"RIFF") or b"WAVE" not in hdr:
                    raise MediaValidationError(
                        "UNSUPPORTED_AUDIO",
                        "Audio file contains invalid or corrupted data and could not be decoded."
                    )
            except OSError:
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


AUDIO_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


async def stream_and_validate_upload(
    upload_file: UploadFile,
    max_bytes: int = MAX_AUDIO_SIZE_BYTES,
) -> Tuple[Path, int, float, str, str]:
    """
    Stream and validate an uploaded audio file.
    Enforces:
    - Non-empty, sanitized filename with supported extension.
    - Bounded streaming read: rejects inputs exceeding max_bytes while reading.
    - Non-empty file content.
    - Decodable media contents and duration <= MAX_AUDIO_DURATION_SECONDS.

    Returns:
    (temp_file_path, size_bytes, duration_seconds, extension, media_type)
    """
    original_filename = upload_file.filename or ""
    sanitized_name = sanitize_filename(original_filename)
    extension = validate_extension(sanitized_name)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file_path = TMP_DIR / f"upload_{uuid.uuid4().hex}{extension}"

    total_bytes = 0
    chunk_size = 64 * 1024  # 64 KiB chunks

    try:
        with open(temp_file_path, "wb") as f_out:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise MediaValidationError(
                        "AUDIO_TOO_LARGE",
                        f"Audio file size exceeds maximum limit of {max_bytes / (1024 * 1024):.0f} MiB."
                    )
                f_out.write(chunk)

        if total_bytes == 0:
            raise MediaValidationError("UNSUPPORTED_AUDIO", "Audio file is empty.")

        # Full media inspection and duration validation
        size_bytes, duration_seconds = validate_audio(temp_file_path)
        media_type = AUDIO_MEDIA_TYPES.get(extension, "application/octet-stream")
        return temp_file_path, size_bytes, duration_seconds, extension, media_type

    except Exception:
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                pass
        raise
