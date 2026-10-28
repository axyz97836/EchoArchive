# EchoArchive v1.0.0 Release Notes

**Release Name:** EchoArchive v1.0.0 — Local-First Traceable Memories  
**Challenge:** Hacktoberfest 2026, Week 4 — *Ghost in the Machine* (October 26–31, 2026)  
**Repository:** [https://github.com/axyz97836/EchoArchive](https://github.com/axyz97836/EchoArchive)  
**License:** MIT License  

---

## Overview

**EchoArchive** is a local-first application designed to preserve authentic spoken oral histories and organize them into **Traceable Memories**. Every AI-generated memory card is strictly grounded in what the speaker actually said, maintaining a direct, verifiable link back to the transcript segments and corresponding original audio.

The original recording and the human-reviewed transcript are the sole authorities; local open-weight AI serves strictly as an indexing and summarization assistant. EchoArchive rejects voice cloning, synthetic avatars, and hallucinated biographies.

---

## Key Features

1. **100% Offline Local Inference:**
   - Speech-to-text recognition powered by `whisper.cpp` (`ggml-tiny.en.bin`) with Apple Metal GPU acceleration.
   - Structured memory extraction powered by local `qwen2.5:1.5b` via Ollama (`http://127.0.0.1:11434`).
   - Zero telemetry, zero analytics, and zero external cloud network calls.
   - Binds strictly to loopback (`127.0.0.1:8766`).

2. **Source-Grounding & Evidence Validation (Traceable Memories):**
   - Every AI-generated memory card cites authoritative transcript segments with start and end timestamps.
   - Server-side `EvidenceValidator` verifies segment provenance and confirms direct quotations against the source transcript.
   - Click-to-seek audio playback streams HTTP 206 Partial Content byte ranges, seeking the audio player directly to the spoken passage.

3. **Human-in-the-Loop Review Gating:**
   - Machine transcripts are marked unreviewed by default (`transcript_reviewed_at = NULL`).
   - Editing any segment increments `transcript_revision` and invalidates review status.
   - Memory extraction strictly rejects unreviewed transcripts at the API boundary (`422 REVIEW_REQUIRED`).
   - Public review bypass attempts (`require_review: false`) are rejected with `422 REVIEW_BYPASS_FORBIDDEN`.
   - Older memory cards are flagged stale when transcripts change and cannot be accepted as current.

4. **100% Local Full-Text Search:**
   - Parameterized SQLite search across story titles, speaker names, chronological transcript segments, memory titles, summaries, and themes.
   - Provides contextual snippet excerpts and audio timestamps for instant playback navigation.

5. **Self-Contained Portable Story Export:**
   - Streams self-contained ZIP archives containing pristine original audio, `story.json`, `transcript.json`, `memories.json`, SHA-256 verified `manifest.json` (`echoarchive-export-v1`), and an offline standalone reader (`story.html`).
   - The offline reader operates with zero remote CDNs, web fonts, or external scripts.
   - Memory cards feature clear `AI Interpretation` badges distinguishing AI summaries from spoken words.

6. **Interruption-Safe Story Deletion:**
   - Story deletion (`DELETE /api/stories/{id}?confirm=true`) uses a staged SQLite cleanup journal (`deletion_journal`) and worker concurrency barriers.
   - Transactionally deletes database rows before unlinking media files.
   - Incomplete deletions resulting from power loss or server crash are automatically reconciled on startup (`recover_pending_deletions`).
   - Active background jobs safely reject deletion with `409 JOB_ACTIVE`.

7. **"Archive After Dark" Archival UI:**
   - High-contrast, accessible visual design (Midnight Ink `#1B252B`, Aged Parchment `#F3E8D6`, Marigold Amber `#E5B65F`, Muted Burgundy `#8C4B4A`).
   - Accessible keyboard navigation, dialog focus trapping, live status announcements, and reduced-motion support.

---

## System Requirements

- **Operating System:** macOS 12+ (tested on macOS 26.6.2, Apple Silicon `arm64`)
- **Processor:** Apple Silicon M1 / M2 / M3 / M4 (8 CPU cores recommended)
- **RAM:** 8 GiB unified memory minimum
- **Disk Space:** ~3 GiB free space for local models and application runtime
- **Python:** Python 3.11 or Python 3.12

---

## Prerequisites & Installation

### 1. System Dependencies (macOS via Homebrew)

```bash
# Install Homebrew if not already installed (https://brew.sh)
brew install ffmpeg whisper-cpp
```

### 2. Ollama & Open-Weight Language Model

1. Download and install Ollama from [https://ollama.com](https://ollama.com).
2. Start Ollama:
   ```bash
   ollama serve
   ```
3. Pull the Qwen 2.5 1.5B model:
   ```bash
   ollama pull qwen2.5:1.5b
   ```

### 3. Repository Setup & Virtual Environment

```bash
git clone https://github.com/axyz97836/EchoArchive.git
cd EchoArchive

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Download Lightweight Whisper Model

```bash
mkdir -p models
curl -L -o models/ggml-tiny.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
```

---

## How to Start EchoArchive

Launch EchoArchive using the included startup helper script:

```bash
./run.sh
```

Or start Uvicorn directly:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8766
```

Open your browser to: **[http://127.0.0.1:8766](http://127.0.0.1:8766)**

---

## Privacy & Security Disclosures

- **Loopback-Only Binding:** The backend binds strictly to `127.0.0.1:8766` and enforces Host and Origin header validation to protect against cross-origin attacks from malicious web pages.
- **Local Storage Encryption:** Stored audio recordings in `data/media/` and SQLite databases reside as unencrypted local files on the host filesystem. Operating system-level disk encryption (e.g. Apple FileVault, Linux LUKS, Windows BitLocker) is required for encryption-at-rest. Localhost binding does not substitute for multi-user operating system boundaries.
- **Physical SSD Deletion:** Story deletion unlinks filesystem pointers and removes database rows. On modern SSDs, underlying flash memory blocks are managed by hardware wear-leveling controllers and do not constitute certified cryptographic forensic erasure.
- **Subprocess Safety:** External binaries (`whisper-cli`, `ffmpeg`) are invoked strictly with argument arrays; `shell=True` is prohibited. Filenames and paths are sanitized against traversal attacks (`../`).
- **Sanitized Errors:** Error responses return standardized codes (`{ "error": { "code": "...", "message": "..." } }`) without leaking server filesystem paths or stack traces.

---

## Known Limitations

1. **Sequential Job Processing:** Background transcription and memory extraction jobs run sequentially (concurrency = 1) to prevent memory contention on 8 GiB RAM laptop environments.
2. **Speech Recognition Performance:** Whisper `tiny.en` provides rapid transcription on Apple Silicon (~0.4x real-time), but challenging acoustic environments or strong non-standard accents may require manual corrections in the transcript review workspace.
3. **Primary Platform:** macOS on Apple Silicon (`arm64`) is the primary verified target. Linux and Windows deployments require separate validation of whisper-cli and FFmpeg binary paths.

---

## Verification & Test Results

- **Automated Test Suite:** **116 passed tests** (115 deterministic unit/integration tests + 1 live speech-and-memory pipeline test) with 100% pass rate.
- **GitHub Actions CI:** Clean passing run on `develop` ([Run #40685495657](https://github.com/axyz97836/EchoArchive/actions/runs/40685495657)).
- **Documentation:** Full architectural specifications available in [`docs/`](docs/).
