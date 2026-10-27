# EchoArchive

> **Stories fade. Their voices don't have to.**

EchoArchive is a local-first application designed to preserve authentic spoken memories and organize them into **Traceable Memories**. Every AI-generated memory card is strictly grounded in what the speaker actually said, maintaining a direct, verifiable link back to the transcript segments and corresponding original audio.

The speaker's recording is the authoritative source of truth; local open-weight AI serves solely as an indexer and summarization assistant—never inventing biographical facts, generating synthetic impersonations, or putting words in someone's mouth.

---

## Challenge Context

- **Challenge:** Hacktoberfest 2026, Week 4 — *Ghost in the Machine* (October 26–31, 2026)
- **Current Milestone:** **Phase D: Premium Frontend, Real Recording & Traceable Memory Experience** (Verified)
- **Target OS:** macOS (Apple Silicon `arm64` verified on Apple M2; Linux conditional on verification)

---

## Phase D Verification Status

Phase D delivers the complete user-facing EchoArchive web application featuring the approved **The Archive After Dark** visual design:

1. **The Archive After Dark Design Foundation:** Crafted with approved palette tokens (Midnight Ink `#1B252B`, Aged Parchment `#F3E8D6`, Marigold Amber `#E5B65F`, Muted Burgundy `#8C4B4A`), editorial system serif headings, high-contrast readable controls, visible focus rings, and WCAG 2.2 AA best practices.
2. **Screen 1: Home / Entry Experience:** Atmospheric landing experience explaining local-only guarantees, real-time readiness status badge, and clear calls to action without fake marketing testimonials.
3. **Screen 2: Real Microphone Studio & Audio Ingest:** Browser microphone recording using `MediaRecorder` (detecting supported MIME types at runtime) with live Web Audio API signal level metering on HTML5 canvas, 5-minute duration cap, explicit consent checkbox, and file upload fallback (WAV, MP3, M4A, FLAC, OGG, WebM <= 25 MiB).
4. **Screen 3: Transcription & Human Review:** Real background job status polling (`queued`, `transcribing`, `succeeded`), master HTML5 audio player with scrub bar and speed toggles, chronological transcript segments, segment-level playback seeking, inline human error correction with atomic optimistic concurrency (`expected_revision`), and explicit review confirmation (`POST /api/stories/{id}/review`).
5. **Screen 4: Memory Extraction Pipeline:** Connects to local Qwen2.5 extraction API with truthful backend stage transitions (`queued`, `analyzing`, `validating`, `saving`, `succeeded`) and actionable recovery paths for offline Ollama or model errors.
6. **Screen 5: Preserved Stories Archive:** Visual library of preserved stories with searchable filtering, duration, revision, and verified memory count badges.
7. **Screen 6: Traceable Memory Cards:** The core experience—prominent memory titles, AI-generated summaries, themes, and **Verified Transcript Evidence** displayed on aged parchment with exact timestamps and "Listen to Spoken Passage" seeking buttons that trigger HTTP 206 byte-range audio playback with synchronized glow highlighting.
8. **Automated Test Suite:** 77 tests (76 deterministic tests + 1 live local inference test) passing with 100% success.

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

### 6. Launch the EchoArchive Web Application (Phase D)

Start the local FastAPI server and open the web application:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8766
```

Then visit [http://127.0.0.1:8766](http://127.0.0.1:8766) in your browser to experience the full 6-screen journey:
- **Home:** System readiness status and local AI verification.
- **Record / Upload:** Microphone recording with live Web Audio level meter and affirmative consent.
- **Transcript Review:** Chronological segments, inline human correction with optimistic concurrency, and review confirmation.
- **Memory Extraction:** Stage stepper tracking local Qwen inference.
- **Archive:** Preserved story library with verified memory counts.
- **Traceable Memory Detail:** Memory cards citing grounded audio passages with click-to-seek playback.

### 7. Run the Automated Test Suite

```bash
# Run all 77 tests (deterministic and live inference)
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
