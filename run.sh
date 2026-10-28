#!/usr/bin/env bash
# EchoArchive — Safe Local Application Launcher
set -euo pipefail

echo "================================================================="
echo " EchoArchive — Starting Local-First Speech Preservation System"
echo "================================================================="

# 1. Check Python virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[-] Error: Python virtual environment (.venv) not found."
    echo "    Please create one: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 2. Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "[!] Warning: ffmpeg not found in PATH."
    echo "    Audio conversion and duration inspection require FFmpeg."
    echo "    Install via Homebrew: brew install ffmpeg"
fi

# 3. Check whisper.cpp CLI
if ! command -v whisper-cli &> /dev/null; then
    echo "[!] Warning: whisper-cli not found in PATH."
    echo "    Speech-to-text requires whisper.cpp CLI."
    echo "    Install via Homebrew: brew install whisper-cpp"
fi

# 4. Check Whisper model
if [ ! -f "models/ggml-tiny.en.bin" ]; then
    echo "[!] Notice: Whisper speech model models/ggml-tiny.en.bin not found."
    echo "    To download: mkdir -p models && curl -L -o models/ggml-tiny.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
fi

# 5. Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "[!] Warning: ollama CLI not found in PATH."
    echo "    Local memory extraction requires Ollama."
    echo "    Download from: https://ollama.com"
fi

# 6. Start EchoArchive API on loopback
echo ""
echo "[+] Starting EchoArchive backend on http://127.0.0.1:8766 (loopback only)..."
echo "    Press Ctrl+C to stop the server."
echo "================================================================="

exec uvicorn backend.main:app --host 127.0.0.1 --port 8766
