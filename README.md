# EchoArchive

> **Stories fade. Their voices don't have to.**

EchoArchive is a local-first application designed to preserve authentic spoken memories and organize them into **Traceable Memories**. Every AI-generated memory card is strictly grounded in what the speaker actually said, maintaining a direct, verifiable link back to the transcript segments and corresponding original audio.

The speaker's recording is the authoritative source of truth; local open-weight AI serves solely as an indexer and summarization assistant—never inventing biographical facts, generating synthetic impersonations, or putting words in someone's mouth.

---

## Challenge Context

- **Challenge:** Hacktoberfest 2026, Week 4 — *Ghost in the Machine* (October 26–31, 2026)
- **Current Milestone:** **Phase A: Foundation & Real Local AI Feasibility** (Verified)
- **Target OS:** macOS (Apple Silicon `arm64` verified on Apple M2; Linux conditional on verification)

---

## Phase A Verification Status

Phase A establishes the project foundation and provides empirical proof that real speech recognition and language model extraction operate fully offline on localhost without cloud APIs:

1. **Local Speech Recognition:** `whisper.cpp` (v1.9.5) with Metal GPU acceleration transcribes synthetic fictional test audio into millisecond-accurate timestamped segments.
2. **Local Memory Extraction:** `Qwen2.5:1.5b` running via local Ollama (`http://127.0.0.1:11434`) generates structured memory cards adhering to a strict schema.
3. **Traceable Grounding Gate:** The server-side evidence validator enforces that every cited source segment ID exists in the transcript and rejects unsupported claims or fabricated quotations.
4. **Automated Test Suite:** 34 tests (33 deterministic unit tests + 1 live local inference test) passing.

---

## Local Architecture

```text
Browser (localhost:8766)
  │ (HTML / Vanilla JS in subsequent phases)
  ▼
FastAPI API Server (Loopback: 127.0.0.1:8766)
  ├── Storage Controller  ──> data/media/ (UUID-based private storage)
  ├── Audio Preprocessor  ──> Local FFmpeg (16 kHz mono WAV normalization)
  ├── Speech Adapter      ──> Local whisper.cpp CLI (Metal GPU accelerated)
  ├── Memory Extraction   ──> Local Qwen2.5:1.5b via Ollama (/api/chat)
  ├── Evidence Validator  ──> Enforces segment citations and anti-hallucination rules
  └── Relational DB       ──> SQLite (PRAGMA foreign_keys = ON, WAL mode)
```

---

## Prerequisites

1. **macOS with Apple Silicon** (tested on macOS 26.6.2 arm64, Apple M2, 8 cores, 8 GiB RAM).
2. **Python 3.11+** (tested on Python 3.12.6).
3. **FFmpeg** (v7.1 installed and executable).
4. **whisper.cpp** (v1.9.5 installed via Homebrew: `brew install whisper-cpp`).
5. **Whisper Speech Model** (`ggml-tiny.en.bin`, ~74.1 MiB).
6. **Ollama** (v0.33.3+ with `qwen2.5:1.5b` model pulled: `ollama pull qwen2.5:1.5b`).

---

## Quickstart & Setup

### 1. Environment Setup

```bash
# Clone and enter directory
cd EchoArchive

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Install Local Speech Model

```bash
# Download lightweight GGML model (~74 MiB) into models/ (gitignored)
mkdir -p models
curl -L -o models/ggml-tiny.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
```

### 3. Verify Local Model Readiness

Run the readiness inspector to verify installed binaries, models, and endpoints:

```bash
python scripts/check_local_models.py
```

### 4. Run the Real Local AI Proof of Concept

Execute the end-to-end smoke demonstration. It generates a short fictional synthetic audio sample, transcribes it locally with `whisper-cli`, extracts memory cards via local `qwen2.5:1.5b`, validates citations, and tests anti-hallucination rejection gates:

```bash
python scripts/smoke_real_inference.py
```

### 5. Run the Automated Test Suite

```bash
# Run all tests (deterministic and live inference)
pytest -v

# Run only deterministic tests (with mocked external processes)
pytest -v -m "not live"

# Run only live inference integration tests
pytest -v -m "live"
```

---

## Privacy, Security, and Ethical Boundaries

EchoArchive adheres to strict privacy and ethical boundaries:

- **100% Offline / Local-Only:** No network calls outside loopback (`127.0.0.1`). Zero analytics, telemetry, or external API keys.
- **Explicit Consent Required:** No microphone recording or audio processing without affirmative user acknowledgment.
- **No Private Data in Git:** Database files, audio files, transcripts, export archives, and model weights are strictly gitignored.
- **No Hallucinated Personas:** No voice cloning, synthetic resurrection, or AI séance personas.
- **Subprocess Safety:** External binaries (`whisper-cli`, `ffmpeg`) are invoked strictly with argument lists; `shell=True` is prohibited. Filenames and paths are sanitized against traversal attacks (`../`).
- **Sanitized Errors:** Error responses return standardized codes (`{ "error": { "code": "...", "message": "..." } }`) without exposing absolute server filesystem paths or stack traces.

---

## Authoritative Documentation

All architectural specifications are maintained inside `docs/`:

- [PRD.md](docs/PRD.md) — Product requirements and acceptance criteria
- [TRD.md](docs/TRD.md) — Technical requirements and engineering boundaries
- [APP_FLOW.md](docs/APP_FLOW.md) — Application state machine and wireflows
- [BACKEND_SCHEMA.md](docs/BACKEND_SCHEMA.md) — SQLite schema and REST API contracts
- [UIUX_BRIEF.md](docs/UIUX_BRIEF.md) — Design system ("Archive After Dark") and palette tokens
- [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — Phased delivery plan (Phases A through F)

---

## License

This project is licensed under the [MIT License](LICENSE).
