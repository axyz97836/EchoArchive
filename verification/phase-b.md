# EchoArchive — Phase B Verification Report: Secure Audio Ingestion, Transcription Jobs & SQLite Persistence

**Date of Execution:** October 28, 2026  
**Repository:** [https://github.com/axyz97836/EchoArchive](https://github.com/axyz97836/EchoArchive)  
**Branch:** `develop` (tracking `origin/develop`)  
**Base Checkpoint:** `70d31c5` (`feat: implement Phase A foundation and real local AI feasibility`)  
**Authoritative Specifications:** `docs/PRD.md`, `docs/TRD.md`, `docs/APP_FLOW.md`, `docs/BACKEND_SCHEMA.md`, `docs/UIUX_BRIEF.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## 1. Executive Summary

Phase B transforms the local speech recognition proof from Phase A into a persistent, production-grade audio ingestion, background processing, and human transcript review pipeline.

All Phase B acceptance criteria have been verified:
1. **Bounded Secure Audio Ingestion:** `POST /api/stories` accepts recordings/uploads, strictly enforces affirmative permission acknowledgment, performs chunk-by-chunk streaming size enforcement (aborting inputs exceeding 25 MiB *while reading*), validates audio decodability and duration (<= 5 minutes), rejects path traversal, and stores media using server-generated UUIDs (`data/media/{uuid}.{ext}`).
2. **In-Process Background Worker:** A dedicated single-worker queue enforces a concurrency ceiling of 1 for heavy inference jobs, transitions through truthful stages (`queued` -> `preparing` -> `transcribing` -> `saving` -> `succeeded`), reports actionable error codes, enforces timeouts, and persists state in SQLite.
3. **Interrupted Job Recovery:** On application startup or restart, `recover_interrupted_jobs()` inspects stranded jobs in `queued` or `running` states and deterministically transitions them to `failed` with code `INTERRUPTED`, safeguarding original recordings.
4. **Durable Storage & Immutable Machine Transcripts:** Initial whisper speech recognition persists timestamped segments in `transcript_segments` with revision 1, while preserving an immutable JSON copy in `data/original_transcripts/{story_id}.json`.
5. **Human Review & Optimistic Revision Control:** `GET /api/stories/{id}/segments` returns chronological segments. `PATCH /api/stories/{id}/segments/{segment_id}` enables human review corrections (e.g. correcting "Coastal Main" to "coastal Maine"), increments `transcript_revision` to 2 via atomic compare-and-swap, and rejects stale updates with HTTP 409 `REVISION_CONFLICT`.
6. **Byte-Range Seekable Audio Streaming:** `GET /api/stories/{id}/audio` supports HTTP Range headers for smooth in-browser `<audio>` element seeking with strict path boundary containment.
7. **Localhost Origin & Host Boundary:** State-changing endpoints reject untrusted browser `Origin` and `Host` headers, eliminating localhost cross-origin request forgery.
8. **Automated Test Coverage:** 63 automated tests (62 deterministic unit/integration tests + 1 live local inference test) passing with zero failures.

---

## 2. Target Environment & Tool Inventory

| Component | Target Requirement | Measured / Verified Environment | Status |
|---|---|---|---|
| **Operating System** | macOS 12+ | macOS 26.6.2 (Darwin arm64, Apple M2) | Verified |
| **CPU / GPU** | Apple Silicon (`arm64`) | 8 CPU cores (`arm64`), Metal GPU `Apple M2` | Verified |
| **System Memory** | 8 GiB minimum | 8.00 GiB unified memory | Verified |
| **Available Disk Space** | > 5 GiB | 10.45 GiB free | Verified |
| **Python** | 3.11+ | Python 3.12.6 (`.venv`) | Verified |
| **Speech Engine** | `whisper.cpp` CLI | `whisper.cpp` v1.9.5 (`/opt/homebrew/bin/whisper-cli`) | Verified |
| **Speech Model** | Open-source GGML | `ggml-tiny.en.bin` (74.1 MiB, MIT License) | Verified |
| **Audio Preprocessor** | Local FFmpeg | FFmpeg v7.1 (`/opt/homebrew/bin/ffmpeg`) | Verified |
| **Language Model Engine**| Local Ollama API | Ollama v0.33.3 at `http://127.0.0.1:11434` | Verified |
| **Language Model** | Open-weight Qwen | `qwen2.5:1.5b` (Q4_K_M GGUF, 986 MiB) | Verified |
| **Database** | SQLite3 with WAL, FK & Migrations | SQLite 3.43.2 (`schema_migrations` tracked) | Verified |

---

## 3. Real Local Integration Workflow Results

The integration script `scripts/smoke_phase_b_integration.py` was executed to verify the full real-world pipeline using a synthetic fictional narrative:

```text
=================================================================
 EchoArchive — Phase B Real Local Ingestion & Transcription Proof
=================================================================

[Step 1/8] Generating synthetic fictional test audio (macOS say)...
  Generated Audio File: phase_b_fictional_test.wav
  File Size:            582.1 KiB

[Step 2/8] Uploading audio with affirmative consent (POST /api/stories)...
  [PASS] Story Created: ID = 0edecba7-874e-455b-8698-9e5d42d1bdc6
         Title:         Grandfather's Wooden Sailboat
         Revision:      0
         Duration:      18.62s
  [PASS] Stored Audio:   media/0edecba7-874e-455b-8698-9e5d42d1bdc6.wav (Verified present)

[Step 3/8] Enqueuing offline transcription job (POST /api/stories/{id}/transcribe)...
  [PASS] Job Accepted:  Job ID = 34dbf564-b4e9-4d4b-bb71-9c6389938121, Initial Stage = queued

[Step 4/8] Polling job state transitions (GET /api/jobs/{job_id})...
  -> Observed Stage: [RUNNING] preparing
  -> Observed Stage: [RUNNING] transcribing
  -> Observed Stage: [SUCCEEDED] succeeded
  [PASS] Whisper Transcription Succeeded in 0.94s

[Step 5/8] Retrieving persisted transcript segments (GET /api/stories/{id}/segments)...
  Story Revision:     1
  Segments Persisted: 6
    [seg-853322f75b73] (00.00s -> 05.24s): When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop
    [seg-e9658c1f34bb] (05.24s -> 06.68s): in Coastal Main.
    [seg-2e62080d0970] (06.68s -> 10.82s): Every Sunday morning in July, we took the boat down to the harbor and watched the white
    [seg-78344980ca8e] (10.82s -> 12.28s): sails catch the wind.
    [seg-41a153dbee15] (12.28s -> 15.40s): He always told me that patience is like trimming the sail.
    [seg-ba745ed6152e] (15.40s -> 18.56s): You cannot control the wind, but you can always guide your boat.

  Identified target segment for review: [seg-e9658c1f34bb] 'in Coastal Main.'

[Step 6/8] Correcting transcription error (PATCH /api/stories/{id}/segments/{seg_id})...
  [PASS] Segment Corrected: 'in Coastal Main.' -> 'in coastal Maine.'
  [PASS] Revision Incremented: 1 -> 2

[Step 7/8] Verifying optimistic concurrency rejection (stale expected_revision=1)...
  [PASS] Stale update correctly rejected: HTTP 409 (REVISION_CONFLICT) Transcript revision mismatch. Expected 1, but current revision is 2.
  [PASS] Immutable original transcript preserved in data/original_transcripts/
  [PASS] Original audio file (0edecba7-874e-455b-8698-9e5d42d1bdc6.wav) remains completely intact (596056 bytes)

[Step 8/8] Re-running Phase A Qwen memory extraction on corrected transcript...
  [PASS] Qwen extracted 1 grounded memory card(s) from corrected transcript:
         Card: 'Building a Wooden Sailboat'
         Summary: My grandfather, Arthur, built a small wooden sailboat in his workshop in coastal Maine when I was seven years old. Every Sunday, we took the boat down to the harbor, where we watched the white sails catch the wind. He always told me that patience is like trimming the sail, and you cannot control the wind, but you can always guide your boat.
         Citations: ['seg-853322f75b73', 'seg-e9658c1f34bb', 'seg-2e62080d0970', 'seg-78344980ca8e', 'seg-ba745ed6152e']

=================================================================
 [SUCCESS] EchoArchive Phase B Real Local Integration Verified!
=================================================================
```

---

## 4. Test Suite Execution & Breakdown

Run command: `.venv/bin/pytest -v`

### Summary:
- **Total Tests:** 63
- **Passed:** 63
- **Failed:** 0
- **Duration:** 7.53s

### Test Coverage Breakdown:

1. `tests/test_api.py` (1 test):
   - `test_api_health_endpoint`: Health readiness reporting for whisper.cpp, FFmpeg, Ollama/Qwen, SQLite, and local storage.
2. `tests/test_database.py` (3 tests):
   - `test_schema_tables_exist`: Table existence check (`stories`, `transcript_segments`, `memory_cards`, `memory_sources`, `jobs`, `schema_migrations`).
   - `test_foreign_key_enforcement`: Foreign key cascading and rejection of orphaned rows.
   - `test_cascade_deletion`: Complete cascade deletion of all segments and jobs when a story is removed.
3. `tests/test_evidence.py` (6 tests):
   - Grounding validation, anti-hallucination gates, and quote verification.
4. `tests/test_extraction.py` (9 tests):
   - Ollama schema extraction, timeout, failure, and malformed JSON resilience.
5. `tests/test_media.py` (7 tests):
   - Input format validation, size caps, duration limits, FFmpeg detection, path traversal checks.
6. `tests/test_transcription.py` (7 tests):
   - Whisper binary availability, model presence, timeout, JSON parsing, chronological segment enforcement.
7. `tests/test_live_inference.py` (1 test):
   - End-to-end live whisper.cpp and Ollama Qwen2.5 memory pipeline on synthetic audio.
8. `tests/test_ingestion.py` (10 tests) — **New in Phase B**:
   - `test_successful_valid_audio_upload`: Audio upload creates story and stores media at generated UUID path.
   - `test_missing_consent_rejected`: Rejection of missing/false `permission_confirmed` with HTTP 422 `CONSENT_REQUIRED`.
   - `test_unsupported_audio_extension_rejected`: Rejection of `.txt`, `.exe`, `.mkv` with HTTP 415 `UNSUPPORTED_AUDIO`.
   - `test_spoofed_mime_type_with_corrupt_content`: Content sniffing rejects corrupt payloads labeled `audio/wav`.
   - `test_empty_audio_upload_rejected`: 0-byte upload rejected with HTTP 415.
   - `test_oversized_streaming_upload_rejected`: Streaming upload aborts when exceeding size cap (`AUDIO_TOO_LARGE`, HTTP 413).
   - `test_audio_exceeding_duration_limit_rejected`: Duration > 300s rejected (`AUDIO_TOO_LONG`, HTTP 422).
   - `test_path_traversal_filename_rejected`: `../` characters rejected (`PATH_TRAVERSAL`, HTTP 422).
   - `test_server_generated_unique_media_paths`: Uploads generate collision-free UUID paths.
   - `test_list_stories_search_and_pagination`: `GET /api/stories` title/speaker filtering and pagination.
9. `tests/test_jobs.py` (6 tests) — **New in Phase B**:
   - `test_enqueue_transcription_and_job_active_conflict`: Enqueueing succeeds; duplicate active job yields HTTP 409 `JOB_ACTIVE`.
   - `test_queue_capacity_limit`: Exceeding max queue depth returns `QUEUE_CAPACITY_EXCEEDED` (HTTP 429).
   - `test_successful_job_execution_lifecycle`: Verifies `queued` -> `preparing` -> `transcribing` -> `saving` -> `succeeded`.
   - `test_transcription_subprocess_failure_persists_error`: Subprocess errors persist `TRANSCRIBER_FAILED` without corrupting story.
   - `test_transcription_timeout_persists_error`: Timeout persists `TRANSCRIBER_TIMEOUT`.
   - `test_interrupted_jobs_recovery_on_startup`: Stranded `queued`/`running` jobs marked `failed` with code `INTERRUPTED` on startup.
10. `tests/test_corrections.py` (6 tests) — **New in Phase B**:
    - `test_transcript_segments_retrieval_order`: Chronological ordering of segments.
    - `test_successful_transcript_correction`: Human review of "Coastal Main" to "coastal Maine", revision increment (1 -> 2), and `user_edited=1`.
    - `test_stale_expected_revision_conflict`: Stale revision returns HTTP 409 `REVISION_CONFLICT`.
    - `test_cross_story_segment_edit_rejected`: Cross-story segment edits rejected with HTTP 404.
    - `test_empty_or_whitespace_correction_rejected`: Empty correction text rejected with HTTP 422.
    - `test_concurrent_corrections_optimistic_concurrency`: Concurrent edits from same revision yield exactly one 200 and one 409.
11. `tests/test_security_audio.py` (7 tests) — **New in Phase B**:
    - `test_full_audio_retrieval`: Standard audio endpoint returns HTTP 200 with `Accept-Ranges: bytes`.
    - `test_audio_byte_range_streaming`: Seekable playback via Range header returns HTTP 206 Partial Content.
    - `test_invalid_byte_range_returns_416`: Out-of-bounds byte range returns HTTP 416.
    - `test_untrusted_origin_rejected`: Untrusted browser Origin blocked with HTTP 403 `FORBIDDEN`.
    - `test_trusted_loopback_origin_accepted`: Loopback Origin (`127.0.0.1`, `localhost`) allowed.
    - `test_untrusted_host_header_rejected`: Malicious Host header blocked with HTTP 403 `FORBIDDEN`.
    - `test_error_response_hygiene`: Errors return sanitized shapes without server paths or stack traces.

---

## 5. Security & Privacy Safeguards

- **Loopback Enforcement:** Binds strictly to `127.0.0.1:8766`. Zero telemetry, zero external network calls.
- **CSRF & DNS Rebinding Protection:** State-changing requests (`POST`, `PATCH`, `DELETE`, `PUT`) validate `Host` and `Origin` headers against allowed loopback domains (`127.0.0.1`, `localhost`, `testserver`), returning HTTP 403 `FORBIDDEN` for external origins.
- **Bounded Streaming Ingestion:** Uploads stream in 64 KiB chunks and terminate immediately if `total_bytes > 25 MiB`, preventing disk or memory exhaustion attacks.
- **Subprocess Safety:** External commands (`ffmpeg`, `whisper-cli`) are executed strictly with list-based arguments without `shell=True`. Timeouts are enforced on all external processes.
- **Sanitized Errors:** Internal exceptions are trapped and returned as `{ "error": { "code": "...", "message": "..." } }`. Local paths, database locations, and python stack traces are never leaked in API responses.
- **Git Hygiene:** SQLite databases (`*.sqlite3`), raw/synthetic user audio recordings, transcripts, and model weights are strictly gitignored.

---

## 6. Database Schema & Migration Changes

The SQLite database now tracks schema versions via the `schema_migrations` table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

- Migration version 1 applies the baseline tables (`stories`, `transcript_segments`, `memory_cards`, `memory_sources`, `jobs`) with `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and `PRAGMA busy_timeout = 30000;`.
- Optimistic concurrency control uses an atomic compare-and-swap SQL pattern:
  `UPDATE stories SET transcript_revision = ?, updated_at = ? WHERE id = ? AND transcript_revision = ?;`
  ensuring concurrent updates are cleanly detected and resolved.

---

## 7. Limitations & Recommendations for Phase C

- **Memory Card Generation:** Phase B focuses on ingestion, transcription, storage, and transcript review. Memory card generation via Qwen and source-grounded linking will be fully wired into REST endpoints in Phase C.
- **Interactive Audio Seeking UI:** The backend now supports HTTP 206 byte-range seeking; the frontend waveform and timestamp-aligned playback controls will be built in Phase D.
- **Direct Microphone Capture:** Browser MediaRecorder with audio level metering will be implemented in Phase D.

---

## 8. Specification Compliance Statement

Phase B strictly complies with all six authoritative documents: `docs/PRD.md`, `docs/TRD.md`, `docs/APP_FLOW.md`, `docs/BACKEND_SCHEMA.md`, `docs/UIUX_BRIEF.md`, and `docs/IMPLEMENTATION_PLAN.md`. No architectural compromises or contradictory changes were introduced.
