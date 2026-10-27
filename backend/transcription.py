"""whisper.cpp transcription adapter for local speech-to-text inference."""

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from backend.config import (
    TMP_DIR,
    WHISPER_CLI_PATH,
    WHISPER_MODEL_PATH,
    WHISPER_TIMEOUT_SECONDS,
)


class TranscriptionError(Exception):
    """Exception raised when speech recognition fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class TranscriptSegment:
    """Represents a validated, timestamped transcript segment."""
    segment_index: int
    start_ms: int
    end_ms: int
    text: str


def check_whisper_available() -> bool:
    """Check if the whisper-cli binary is executable."""
    try:
        proc = subprocess.run(
            [WHISPER_CLI_PATH, "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def check_whisper_model_available() -> bool:
    """Check if the configured Whisper model exists and has non-zero size."""
    return WHISPER_MODEL_PATH.exists() and WHISPER_MODEL_PATH.stat().st_size > 0


def transcribe_audio_file(
    audio_wav_path: Path,
    model_path: Optional[Path] = None,
    whisper_bin: Optional[str] = None,
    timeout: Optional[int] = None,
) -> List[TranscriptSegment]:
    """
    Transcribe a 16 kHz mono WAV file using local whisper.cpp.
    Returns a list of chronological, validated TranscriptSegments.
    """
    bin_path = whisper_bin or WHISPER_CLI_PATH
    selected_model = model_path or WHISPER_MODEL_PATH
    call_timeout = timeout or WHISPER_TIMEOUT_SECONDS

    # Verify binary availability
    try:
        test_proc = subprocess.run([bin_path, "--version"], capture_output=True, timeout=5, check=False)
        if test_proc.returncode != 0:
            raise TranscriptionError("TRANSCRIBER_UNAVAILABLE", f"whisper-cli exited with code {test_proc.returncode}.")
    except (FileNotFoundError, OSError) as e:
        raise TranscriptionError(
            "TRANSCRIBER_UNAVAILABLE",
            f"whisper-cli binary not found at '{bin_path}'. Please install whisper.cpp."
        )

    # Verify model availability
    if not selected_model.exists() or selected_model.stat().st_size == 0:
        raise TranscriptionError(
            "TRANSCRIBER_UNAVAILABLE",
            f"Whisper model file not found at '{selected_model}'. Please install a GGML model."
        )

    # Prepare temporary output file path
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_id = uuid.uuid4().hex
    output_base = TMP_DIR / f"whisper_out_{temp_id}"
    json_output_path = TMP_DIR / f"whisper_out_{temp_id}.json"

    # Assemble argument array strictly without shell=True
    cmd = [
        bin_path,
        "-m", str(selected_model),
        "-f", str(audio_wav_path),
        "-l", "en",
        "-oj",
        "-of", str(output_base),
        "--no-prints",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=call_timeout,
            check=False,
        )
        if proc.returncode != 0:
            err_msg = proc.stderr.strip()[:300] if proc.stderr else f"Exit code {proc.returncode}"
            raise TranscriptionError(
                "TRANSCRIBER_FAILED",
                f"whisper-cli failed during inference: {err_msg}"
            )

        if not json_output_path.exists():
            raise TranscriptionError(
                "INVALID_TRANSCRIPTION_OUTPUT",
                "whisper-cli did not generate expected JSON output file."
            )

        with open(json_output_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as jde:
                raise TranscriptionError(
                    "INVALID_TRANSCRIPTION_OUTPUT",
                    f"Malformed JSON output from whisper-cli: {str(jde)}"
                )

        raw_segments = data.get("transcription", [])
        if not isinstance(raw_segments, list):
            raise TranscriptionError(
                "INVALID_TRANSCRIPTION_OUTPUT",
                "Transcription JSON missing 'transcription' segment list."
            )

        validated_segments: List[TranscriptSegment] = []
        last_start = -1

        for idx, item in enumerate(raw_segments):
            offsets = item.get("offsets", {})
            start_ms = offsets.get("from")
            end_ms = offsets.get("to")
            raw_text = item.get("text", "")
            text = raw_text.strip()

            if start_ms is None or end_ms is None or not isinstance(start_ms, int) or not isinstance(end_ms, int):
                raise TranscriptionError(
                    "INVALID_TRANSCRIPTION_OUTPUT",
                    f"Segment {idx} has invalid timestamp offsets: {offsets}"
                )

            if start_ms < 0:
                raise TranscriptionError(
                    "INVALID_TRANSCRIPTION_OUTPUT",
                    f"Segment {idx} has negative start_ms ({start_ms})."
                )

            if end_ms <= start_ms:
                # Minimum duration enforcement for edge cases
                end_ms = start_ms + 100

            if start_ms < last_start:
                raise TranscriptionError(
                    "INVALID_TRANSCRIPTION_OUTPUT",
                    f"Segment {idx} start_ms ({start_ms}) is not chronological (last: {last_start})."
                )
            last_start = start_ms

            if not text:
                continue  # skip silent tokens

            validated_segments.append(
                TranscriptSegment(
                    segment_index=len(validated_segments),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )
            )

        return validated_segments

    except subprocess.TimeoutExpired:
        raise TranscriptionError(
            "TRANSCRIBER_TIMEOUT",
            f"whisper-cli inference timed out after {call_timeout} seconds."
        )
    finally:
        # Cleanup intermediate files
        for p in (json_output_path, Path(f"{output_base}.txt"), Path(f"{output_base}.srt"), Path(f"{output_base}.vtt")):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
