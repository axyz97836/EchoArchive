# EchoArchive

> **Stories fade. Their voices don't have to.**

EchoArchive is a local-first application designed to preserve authentic spoken memories and organize them into **Traceable Memories**. Every AI-generated memory card is strictly grounded in what the speaker actually said, maintaining a direct, verifiable link back to the transcript segments and corresponding original audio.

The speaker's recording is the authoritative source of truth; local open-weight AI serves solely as an indexer and summarization assistant—never inventing biographical facts, generating synthetic impersonations, or putting words in someone's mouth.

---

## Challenge Context

- **Challenge:** Hacktoberfest 2026, Week 4 — *Ghost in the Machine* (October 26–31, 2026)
- **Current Milestone:** **Phase B: Secure Audio Ingestion, Transcription Jobs & SQLite Persistence** (Verified)
- **Target OS:** macOS (Apple Silicon `arm64` verified on Apple M2; Linux conditional on verification)

---

## Phase B Verification Status

Phase B converts the local transcription proof into a reliable, persistent audio ingestion and human review workflow:

1. **Secure Ingestion Pipeline:** `POST /api/stories` enforces bounded chunk streaming (rejecting oversized uploads while reading rather than buffering), strict affirmative consent confirmation, 25 MiB file ceiling, 5-minute duration cap, decodability validation, and server-generated UUID storage (`data/media/{uuid}.{ext}`).
2. **In-Process Transcription Worker:** Bounded queue with maximum concurrency of 1, persisted SQLite state, truthful stage reporting (`queued` -> `preparing` -> `transcribing` -> `saving` -> `succeeded`), actionable error codes, and subprocess timeout enforcement.
3. **Startup Crash Recovery:** Automatically identifies stranded jobs on startup and marks them as `failed` with code `INTERRUPTED`, preserving original media and preventing partial duplicates.
4. **Traceable Review & Revision Tracking:** `GET /api/stories/{id}/segments` provides chronological timestamped segments. `PATCH /api/stories/{id}/segments/{segment_id}` enables human correction with atomic optimistic concurrency control (`expected_revision`), incrementing `transcript_revision` and preserving the immutable machine-generated transcript in `data/original_transcripts/{story_id}.json`.
5. **Seekable Audio Streaming:** `GET /api/stories/{id}/audio` provides seekable HTTP Range byte streaming for in-browser playback without path traversal.
6. **Localhost Security Middleware:** Rejects untrusted browser Origin and Host headers on state-changing requests, eliminating localhost CSRF/rebinding attack surfaces.
7. **Automated Test Suite:** 63 tests (62 deterministic tests + 1 live local inference test) passing.

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

### 4. Run the Real Local AI Proof of Concept (Phase A)

Execute the end-to-end Phase A smoke demonstration (whisper.cpp + local Qwen memory card extraction):

```bash
python scripts/smoke_real_inference.py
```

### 5. Run the Phase B Ingestion, Job & Human Review Verification

Execute the complete Phase B workflow (synthetic audio ingestion -> background job state transitions -> whisper.cpp transcription -> segment review -> human error correction ("Coastal Main" -> "coastal Maine") -> revision increment -> optimistic concurrency validation):

```bash
python scripts/smoke_phase_b_integration.py
```

### 6. Run the Automated Test Suite

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
