# EchoArchive

> **Stories fade. Their voices don't have to.**

EchoArchive is a local-first application designed to preserve authentic spoken memories and organize them into **Traceable Memories**. Every AI-generated memory card is strictly grounded in what the speaker actually said, maintaining a direct, verifiable link back to the transcript segments and corresponding original audio.

The speaker's recording is the authoritative source of truth; local open-weight AI serves solely as an indexer and summarization assistant—never inventing biographical facts, generating synthetic impersonations, or putting words in someone's mouth.

---

## Challenge Context

- **Challenge:** Hacktoberfest 2026, Week 4 — *Ghost in the Machine* (October 26–31, 2026)
- **Current Milestone:** **Phase F: Final Security Hardening, Comprehensive Verification & Release Preparation** (Verified)
- **Target OS:** macOS (Apple Silicon `arm64` verified on Apple M2; Linux conditional on verification)

---

## Phase F Verification Status

Phase F delivers final security hardening, robust transcript review enforcement at the backend API boundary, durable interruption-safe deletion journaling, audited portable ZIP exports, and comprehensive end-to-end verification:

1. **Enforced Transcript Review at API Boundary:** Machine-generated transcripts start strictly unreviewed (`transcript_reviewed_at = NULL`). Segment corrections invalidate review confirmation and mark prior memory cards stale. Memory extraction unconditionally rejects unreviewed transcripts (`422 REVIEW_REQUIRED`), public bypass attempts (`require_review: false`) are rejected with `422 REVIEW_BYPASS_FORBIDDEN`, and regeneration after re-review uses the latest transcript revision.
2. **Durable Crash-Safe Deletion Journal:** Story deletion (`DELETE /api/stories/{id}?confirm=true`) uses a staged SQLite cleanup journal (`deletion_journal`) and worker concurrency lock. Deletion transactionally removes database records before unlinking media files. In the event of an unexpected interruption or power loss, pending unlinks are automatically reconciled on server startup or repeated delete invocation (`recover_pending_deletions`). Active jobs safely reject deletion with `409 JOB_ACTIVE`.
3. **Audited Portable Story Export:** Streaming ZIP generator (`GET /api/stories/{id}/export`) embeds pristine original audio bytes, `story.json`, `transcript.json`, `memories.json`, SHA-256 verified `manifest.json` (`echoarchive-export-v1`), and an offline standalone reader (`story.html`). Memory cards are explicitly labeled as `AI Interpretation`, all user content is HTML-escaped, and concurrent edits raise `409 REVISION_CONFLICT` to prevent corrupt exports.
4. **Local Full-Text Search:** 100% offline parameterized SQLite search (`GET /api/search?q=...`) across story titles, speaker labels, chronological transcript segments, memory card titles, summaries, and themes with contextual snippets and direct audio seeking timestamps.
5. **Real Local AI Verification:** Genuine offline inference runs verified on Apple Silicon: `whisper.cpp` (`ggml-tiny.en.bin`) for Metal GPU speech recognition and `qwen2.5:1.5b` via local Ollama for grounded memory extraction.
6. **Automated Test Suite:** **116 automated tests passed** (115 deterministic unit/integration tests + 1 live speech-and-memory pipeline test) with 100% pass rate.

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

### 6. Launch the EchoArchive Web Application

Start the local server using the startup helper or directly via Uvicorn:

```bash
# Using the startup helper (verifies dependencies and starts on loopback)
./run.sh

# Or directly with uvicorn:
uvicorn backend.main:app --host 127.0.0.1 --port 8766
```

Then visit [http://127.0.0.1:8766](http://127.0.0.1:8766) in your browser to experience the full 6-screen journey:
- **Home:** System readiness status and local AI verification.
- **Record / Upload:** Microphone recording with live Web Audio level meter and affirmative consent.
- **Transcript Review:** Chronological segments, inline human correction with optimistic concurrency, and review confirmation.
- **Memory Extraction:** Stage stepper tracking local Qwen inference.
- **Archive:** Preserved story library with full-text search and verified memory counts.
- **Traceable Memory Detail:** Memory cards citing grounded audio passages with click-to-seek playback.
- **Data Governance:** Portable self-contained ZIP export and safe, journaled story deletion.

### 7. Run the Automated Test Suite

```bash
# Run all 116 tests (deterministic and live inference)
pytest -v

# Run only deterministic tests (with mocked external processes)
pytest -v -m "not live"

# Run only live inference integration tests
pytest -v -m "live"
```

### 8. Run Full End-to-End Real Local AI Verification

Execute the complete 15-step real-world integration verification on localhost:

```bash
python scripts/smoke_phase_f_full_e2e.py
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
