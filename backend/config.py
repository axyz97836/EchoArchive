"""Configuration and runtime boundaries for EchoArchive."""

import os
import shutil
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Server loopback configuration
HOST = os.getenv("ECHOARCHIVE_HOST", "127.0.0.1")
PORT = int(os.getenv("ECHOARCHIVE_PORT", "8766"))

# Media and duration limits
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MiB
MAX_AUDIO_DURATION_SECONDS = 300.0        # 5 minutes (300 seconds)
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}

# Storage directories
DATA_DIR = Path(os.getenv("ECHOARCHIVE_DATA_DIR", PROJECT_ROOT / "data"))
MEDIA_DIR = DATA_DIR / "media"
ORIGINAL_TRANSCRIPTS_DIR = DATA_DIR / "original_transcripts"
TMP_DIR = DATA_DIR / "tmp"
DATABASE_PATH = DATA_DIR / "echoarchive.sqlite3"

# Speech recognition (whisper.cpp)
WHISPER_CLI_PATH = os.getenv(
    "ECHOARCHIVE_WHISPER_BIN",
    shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli" or "whisper-cli"
)
WHISPER_MODEL_PATH = Path(
    os.getenv("ECHOARCHIVE_WHISPER_MODEL", PROJECT_ROOT / "models" / "ggml-tiny.en.bin")
)
WHISPER_TIMEOUT_SECONDS = int(os.getenv("ECHOARCHIVE_WHISPER_TIMEOUT", "120"))

# LLM Memory Extraction (Ollama + Qwen2.5)
OLLAMA_BASE_URL = os.getenv("ECHOARCHIVE_OLLAMA_URL", "http://127.0.0.1:11434")
QWEN_MODEL_NAME = os.getenv("ECHOARCHIVE_QWEN_MODEL", "qwen2.5:1.5b")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("ECHOARCHIVE_OLLAMA_TIMEOUT", "60"))

# FFmpeg tool
FFMPEG_BIN_PATH = os.getenv(
    "ECHOARCHIVE_FFMPEG_BIN",
    shutil.which("ffmpeg")
    or str(Path.home() / ".local" / "bin" / "ffmpeg")
    or "/opt/homebrew/bin/ffmpeg"
    or "ffmpeg"
)


def ensure_storage_directories() -> None:
    """Ensure runtime storage directories exist with restricted permissions."""
    for path in (MEDIA_DIR, ORIGINAL_TRANSCRIPTS_DIR, TMP_DIR):
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
