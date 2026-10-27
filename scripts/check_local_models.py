#!/usr/bin/env python3
"""Inspect local environment, binaries, and local AI model readiness."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    FFMPEG_BIN_PATH,
    OLLAMA_BASE_URL,
    QWEN_MODEL_NAME,
    WHISPER_CLI_PATH,
    WHISPER_MODEL_PATH,
)
from backend.extraction import check_ollama_available, check_qwen_model_available
from backend.media import check_ffmpeg_available
from backend.transcription import check_whisper_available, check_whisper_model_available


def main() -> int:
    print("==================================================")
    print(" EchoArchive — Local Environment Readiness Check")
    print("==================================================")

    # OS & Architecture
    print(f"\n[OS & System]")
    print(f"  Platform:         {platform.platform()}")
    print(f"  Machine/Arch:     {platform.machine()}")
    print(f"  Python:           {sys.version.split()[0]} ({sys.executable})")

    # Disk & Memory
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    print(f"  Disk Space Free:  {free / (1024**3):.2f} GiB (Total: {total / (1024**3):.2f} GiB)")

    # FFmpeg
    print(f"\n[Audio Preprocessor — FFmpeg]")
    ffmpeg_ok = check_ffmpeg_available()
    print(f"  Path:             {FFMPEG_BIN_PATH}")
    print(f"  Status:           {'READY' if ffmpeg_ok else 'MISSING / ERROR'}")
    if ffmpeg_ok:
        try:
            ver = subprocess.run([FFMPEG_BIN_PATH, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
            print(f"  Version:          {ver}")
        except Exception:
            pass

    # whisper.cpp
    print(f"\n[Speech Recognition — whisper.cpp]")
    whisper_ok = check_whisper_available()
    print(f"  CLI Path:         {WHISPER_CLI_PATH}")
    print(f"  CLI Status:       {'READY' if whisper_ok else 'MISSING / ERROR'}")
    if whisper_ok:
        try:
            ver = subprocess.run([WHISPER_CLI_PATH, "--version"], capture_output=True, text=True).stdout.strip()
            print(f"  CLI Version:      {ver}")
        except Exception:
            pass

    model_ok = check_whisper_model_available()
    print(f"  Model Path:       {WHISPER_MODEL_PATH}")
    print(f"  Model Status:     {'READY' if model_ok else 'MISSING'}")
    if model_ok:
        sz = WHISPER_MODEL_PATH.stat().st_size / (1024 * 1024)
        print(f"  Model Size:       {sz:.1f} MiB")

    # Ollama & Qwen
    print(f"\n[Language Model — Ollama & Qwen]")
    ollama_ok = check_ollama_available()
    print(f"  Endpoint:         {OLLAMA_BASE_URL}")
    print(f"  Ollama Status:    {'READY' if ollama_ok else 'NOT REACHABLE'}")

    qwen_ok = check_qwen_model_available() if ollama_ok else False
    print(f"  Target Model:     {QWEN_MODEL_NAME}")
    print(f"  Model Status:     {'INSTALLED' if qwen_ok else 'NOT FOUND'}")

    # Overall gate
    print("\n--------------------------------------------------")
    all_ready = ffmpeg_ok and whisper_ok and model_ok and ollama_ok and qwen_ok
    if all_ready:
        print(" [PASS] All local AI prerequisites are READY for offline execution.")
        return 0
    else:
        print(" [FAIL] Some local dependencies are missing. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
