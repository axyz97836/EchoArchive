# EchoArchive — Phase A Verification Report: Foundation & Real Local AI Feasibility

**Date of Execution:** October 28, 2026  
**Repository:** [https://github.com/axyz97836/EchoArchive](https://github.com/axyz97836/EchoArchive)  
**Branch:** `develop` (tracking `origin/develop`)  
**Base Checkpoint:** `1ba0566` (`docs: relocate planning documents to docs/ directory`)  
**Authoritative Specifications:** `docs/PRD.md`, `docs/TRD.md`, `docs/APP_FLOW.md`, `docs/BACKEND_SCHEMA.md`, `docs/UIUX_BRIEF.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## 1. Executive Summary

Phase A demonstrates the core offline AI feasibility of EchoArchive: **transforming spoken audio into source-grounded memory cards on localhost without external cloud APIs or third-party inference services**.

All Phase A verification gates have been passed:
- `whisper.cpp` (v1.9.5) compiled with Metal GPU acceleration was installed and verified on macOS Apple Silicon.
- The official `ggml-tiny.en.bin` model (74.1 MiB) was downloaded and verified for offline speech recognition.
- `qwen2.5:1.5b` running via local Ollama (`http://127.0.0.1:11434`) was verified for structured memory extraction.
- The server-side evidence validator was implemented and verified to enforce that every memory card references valid transcript segments and rejects hallucinated assertions or fabricated quotations.
- 34 automated tests (33 deterministic unit tests + 1 live local inference test) were executed and passed.

---

## 2. macOS Target Environment & Tool Inventory

| Component | Target Requirement | Measured / Verified Environment | Status |
|---|---|---|---|
| **Operating System** | macOS 12+ | macOS 26.6.2 (Darwin arm64, Apple M2) | Verified |
| **CPU Architecture** | Apple Silicon (`arm64`) | 8 CPU cores (`arm64`), Metal GPU `Apple M2` | Verified |
| **System Memory** | 8 GiB minimum | 8.00 GiB unified memory | Verified |
| **Available Disk Space** | > 5 GiB | 10.58 GiB free | Verified |
| **Python** | 3.11+ | Python 3.12.6 (`/Library/.../python3.12`) | Verified |
| **Speech Engine** | `whisper.cpp` CLI | `whisper.cpp` v1.9.5 (`/opt/homebrew/bin/whisper-cli`) | Verified |
| **Speech Model** | Open-source GGML | `ggml-tiny.en.bin` (74.1 MiB, MIT License) | Verified |
| **Audio Preprocessor** | Local FFmpeg | FFmpeg v7.1 (`/Users/.../.local/bin/ffmpeg`) | Verified |
| **Language Model Engine**| Local Ollama API | Ollama v0.33.3 at `http://127.0.0.1:11434` | Verified |
| **Language Model** | Open-weight Qwen | `qwen2.5:1.5b` (Q4_K_M GGUF, 986 MiB) | Verified |
| **Database** | SQLite3 with WAL & FK | SQLite 3.43.2 (with `PRAGMA foreign_keys = ON;`) | Verified |

---

## 3. Real Local AI Proof of Concept Results

The reproducible verification command `python scripts/smoke_real_inference.py` was executed with a synthetic, fictional English audio sample:

```text
Story Text: "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop in coastal Maine. Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. He always told me that patience is like trimming the sail: you cannot control the wind, but you can always guide your boat."
```

### Observed Execution Log:

```text
=================================================================
 EchoArchive — Real Local AI Proof of Concept (Phase A)
=================================================================

[Step 1/5] Generating synthetic test audio (fictional story)...
  Synthetic Audio File: synthetic_fictional_test.wav
  File Size:            582.1 KiB
  Decoded Duration:     18.62 seconds
  Text Source:          Fictional narrative (zero personal data)

[Step 2/5] Running real local whisper.cpp speech recognition...
  Transcription Time:   1.24 seconds (Metal GPU accelerated)
  Segments Detected:    6

  --- Real Timestamped Transcript Segments ---
  [seg-000] (00.00s -> 05.24s): When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop
  [seg-001] (05.24s -> 06.68s): in Coastal Main.
  [seg-002] (06.68s -> 10.82s): Every Sunday morning in July, we took the boat down to the harbor and watched the white
  [seg-003] (10.82s -> 12.28s): sails catch the wind.
  [seg-004] (12.28s -> 15.40s): He always told me that patience is like trimming the sail.
  [seg-005] (15.40s -> 18.56s): You cannot control the wind, but you can always guide your boat.

[Step 3/5] Extracting structured memory cards via local Qwen2.5:1.5b...
  Extraction Time:      4.20 seconds
  Memory Cards Found:   1

[Step 4/5] Validating source evidence citations against transcript...

  --- Verified Grounded Memory Cards ---

  [Memory Card #1]
    Title:       Building a Wooden Sailboat
    Summary:     My grandfather built a small wooden sailboat in his workshop in Coastal Main. Every Sunday, we took the boat down to the harbor and watched the white sails catch the wind. He always told me that patience is like trimming the sail, and you cannot control the wind, but you can always guide your boat.
    Themes:      Grandfather's Boat Building, Patience and Guidance
    Citations:   ['seg-000', 'seg-001', 'seg-002', 'seg-003', 'seg-004', 'seg-005']
    Supporting Passages from Recording:
      - [seg-000]: "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop"
      - [seg-001]: "in Coastal Main."
      - [seg-002]: "Every Sunday morning in July, we took the boat down to the harbor and watched the white"
      - [seg-003]: "sails catch the wind."
      - [seg-004]: "He always told me that patience is like trimming the sail."
      - [seg-005]: "You cannot control the wind, but you can always guide your boat."

[Step 5/5] Testing anti-hallucination & provenance rejection gates...
  [PASS] Nonexistent segment reference correctly rejected: (INVALID_EVIDENCE) Memory card 'Invented Family Dinner' cites nonexistent or cross-story segment ID 'seg-999'.
  [PASS] Fabricated quotation correctly rejected: (UNSUPPORTED_QUOTE) Card 'Sailing Wisdom' includes alleged quotation 'We will always conquer the stormy Atlantic ocean!' which is not present in cited source segments.

=================================================================
 [SUCCESS] EchoArchive Phase A Real Local AI Proof Verified!
=================================================================
```

---

## 4. Test Suite Execution

Run command: `.venv/bin/pytest -v`

### Summary:
- **Total Tests:** 34
- **Passed:** 34
- **Failed:** 0
- **Duration:** 5.01s

### Test Coverage Breakdown:
1. `tests/test_api.py` (1 test):
   - `test_api_health_endpoint`: Verifies `/api/health` status, truthful service reporting, engine types, and storage boundaries.
2. `tests/test_database.py` (3 tests):
   - `test_schema_tables_exist`: Verifies all 5 tables (`stories`, `transcript_segments`, `memory_cards`, `memory_sources`, `jobs`) exist.
   - `test_foreign_key_enforcement`: Confirms `PRAGMA foreign_keys = ON;` prevents inserting orphaned records.
   - `test_cascade_deletion`: Confirms deleting a story removes all associated segments, cards, and source links.
3. `tests/test_evidence.py` (6 tests):
   - `test_valid_evidence_citations`: Grounding in existing segments extracts matching supporting text.
   - `test_nonexistent_segment_citation_rejected`: Citation to missing segment raises `INVALID_EVIDENCE`.
   - `test_empty_citations_rejected`: Card without citations raises `INVALID_EVIDENCE`.
   - `test_unsupported_quotation_rejected`: Fabricated quote in summary raises `UNSUPPORTED_QUOTE`.
   - `test_supported_quotation_accepted`: Verbatim quotation present in transcript passes.
   - `test_batch_validation_rejects_on_any_invalid`: Batch validation is atomic.
4. `tests/test_extraction.py` (9 tests):
   - `test_ollama_unavailable_raises_error`: Simulates Ollama offline -> `OLLAMA_UNAVAILABLE`.
   - `test_ollama_timeout_raises_error`: Simulates request timeout -> `OLLAMA_TIMEOUT`.
   - `test_ollama_http_failure`: Simulates HTTP 500 -> `OLLAMA_FAILED`.
   - `test_malformed_qwen_json`: Simulates invalid JSON text -> `INVALID_AI_OUTPUT`.
   - `test_missing_cards_array`: Simulates missing `cards` key -> `INVALID_AI_OUTPUT`.
   - `test_missing_title_in_card`: Card missing title -> `INVALID_AI_OUTPUT`.
   - `test_title_too_long`: Card title > 160 chars -> `INVALID_AI_OUTPUT`.
   - `test_missing_source_segment_ids`: Card missing source IDs -> `INVALID_EVIDENCE`.
   - `test_valid_qwen_extraction`: Valid mock response parsing into `RawMemoryCard`.
5. `tests/test_media.py` (7 tests):
   - `test_valid_audio_input`: Valid 5-second PCM WAV passes validation.
   - `test_unsupported_audio_formats`: Rejects `.txt`, `.exe`, `.mkv` with `UNSUPPORTED_AUDIO`.
   - `test_audio_exceeding_25_mib`: Enforces 25 MiB cap -> `AUDIO_TOO_LARGE`.
   - `test_audio_exceeding_five_minutes`: Enforces 300s cap -> `AUDIO_TOO_LONG`.
   - `test_corrupted_or_invalid_audio`: Corrupt data -> `UNSUPPORTED_AUDIO`.
   - `test_missing_ffmpeg`: Missing binary -> `FFMPEG_UNAVAILABLE`.
   - `test_path_traversal_detection`: Path traversal attempts (`../../`) -> `PATH_TRAVERSAL`.
6. `tests/test_transcription.py` (7 tests):
   - `test_missing_whisper_binary`: Missing CLI -> `TRANSCRIBER_UNAVAILABLE`.
   - `test_missing_whisper_model`: Missing GGML file -> `TRANSCRIBER_UNAVAILABLE`.
   - `test_transcription_timeout`: Subprocess timeout -> `TRANSCRIBER_TIMEOUT`.
   - `test_transcription_subprocess_failure`: Subprocess exit code 1 -> `TRANSCRIBER_FAILED`.
   - `test_malformed_whisper_json_output`: Malformed JSON -> `INVALID_TRANSCRIPTION_OUTPUT`.
   - `test_non_chronological_segments_rejected`: Inverted timestamps -> `INVALID_TRANSCRIPTION_OUTPUT`.
   - `test_valid_transcription_parsing`: Valid whisper JSON parsing into `TranscriptSegment`.
7. `tests/test_live_inference.py` (1 test):
   - `test_genuine_local_speech_and_memory_pipeline`: Executes real `whisper-cli` transcription and real `qwen2.5:1.5b` extraction on a fresh synthetic audio sample, verifying end-to-end local inference and grounding.

---

## 5. Security & Privacy Audit

- **Network Boundary:** Server binds strictly to loopback (`127.0.0.1:8766`). Zero outbound HTTP requests to cloud AI services or analytics trackers.
- **Subprocess Safety:** External commands (`whisper-cli`, `ffmpeg`) use explicit argument arrays; `shell=True` is prohibited across all modules.
- **Git Hygiene:**
  - `data/` (SQLite databases, audio recordings, transcripts) is strictly gitignored.
  - `models/` (GGML/GGUF weights) is strictly gitignored.
  - `.venv/` is strictly gitignored.
  - No secret keys, private credentials, or personal audio recordings are present in the repository or git history.
- **Input Boundaries:** 25 MiB upload ceiling and 5-minute (300-second) duration limits enforced.

---

## 6. Specification Notes & Discrepancies

- In `docs/IMPLEMENTATION_PLAN.md` line 227, an initial proposal suggested keeping the six planning documents at the root of a new repository. However, checkpoint `1ba0566` relocated all six documents into `docs/`, and project instructions explicitly mandate keeping all six documents inside `docs/` without moving, renaming, deleting, or duplicating them. All project modules and verification tests reference `docs/` as the single authoritative source.

---

## 7. Limitations & Recommendations for Phase B

- **Single-Job Worker:** Phase A verifies the local inference adapters; Phase B will integrate the in-process SQLite job queue and background worker to handle asynchronous ingest and transcription.
- **REST Endpoints:** Audio upload (`POST /api/stories`), segment correction (`PATCH /api/stories/{id}/segments/{segment_id}`), and card listing endpoints will be implemented in Phase B and Phase C.
- **Microphone UI:** Frontend audio capture with permission handling will be built in Phase D.
