# EchoArchive — Phase C Verification Report: Traceable Memories, Grounded AI Extraction & Playback

**Date of Execution:** October 28, 2026  
**Repository:** [https://github.com/axyz97836/EchoArchive](https://github.com/axyz97836/EchoArchive)  
**Branch:** `develop` (tracking `origin/develop`)  
**Base Checkpoint:** `a005770` (`fix(ci): add ffmpeg dependency, isolate test directories, and tune worker polling`)  
**Authoritative Specifications:** `docs/PRD.md`, `docs/TRD.md`, `docs/APP_FLOW.md`, `docs/BACKEND_SCHEMA.md`, `docs/UIUX_BRIEF.md`, `docs/IMPLEMENTATION_PLAN.md`

---

## 1. Executive Summary

Phase C implements the defining capability of EchoArchive: **Traceable Memories**. Every AI-generated memory card is strictly grounded in genuine, human-reviewed spoken transcript segments and connected directly to seekable, original-audio playback on localhost.

All Phase C acceptance gates have been implemented and verified:
1. **Schema-Constrained Local Extraction:** Memory cards are extracted using local `qwen2.5:1.5b` via Ollama (`http://127.0.0.1:11434`) strictly bounded by JSON schemas requesting concise titles, summaries, themes, and explicit source segment IDs.
2. **Server-Side Grounding & Evidence Validation:** Cards are validated by `validate_memory_cards_batch`. Nonexistent segment IDs, cross-story segment IDs, empty citations, and hallucinated direct quotations not present in cited segments are deterministically rejected with atomic transaction rollback.
3. **Truthful Review Lifecycle:** Memory cards are stored with `review_state = 'draft'`. AI summaries are explicitly designated as interpretations requiring human verification rather than accepted as infallible truth. Users review and approve cards via `PATCH /api/cards/{id}`.
4. **Transcript Revision Integrity & Stale Detection:** Memory cards are permanently tagged with `generated_from_revision`. When human transcript edits advance a story's revision (e.g. from Revision 2 to 3), previously generated memory cards are dynamically flagged as `is_stale = true` with actionable explanations.
5. **Inference Concurrency & Race-Condition Safeguards:** The worker enforces transactional compare-and-swap checks during card persistence: if a user edits a transcript while inference is in flight, the generation result is rejected with `REVISION_CONFLICT`, preventing stale cards from being saved as current.
6. **No-Duplicate Regeneration:** Re-running memory extraction for a newer transcript revision replaces outdated cards and their source relationships in a single atomic transaction, preventing duplicate card accumulation.
7. **Source-Linked Seekable Audio Playback:** Each cited source segment delivers start/end timestamps, duration, timing reliability flags, and direct links to HTTP 206 Partial Content byte-range streams, allowing users to immediately hear the exact recorded moment.
8. **Minimal Functional Playback Demonstration Harness:** Served at `/demo` and `/phase-c-demo`, enabling browser-level testing of story selection, memory inspection, one-click audio seeking to segment timestamps, transcript editing, and live stale card invalidation.
9. **Automated Test Suite:** 74 tests passing (73 deterministic unit/integration tests covering offline, timeout, malformed JSON, invalid citations, race conditions, stale invalidation, and byte-range seeking, plus 1 live local speech-and-memory pipeline test).

---

## 2. Target Environment & Tool Inventory

| Component | Target Requirement | Measured / Verified Environment | Status |
|---|---|---|---|
| **Operating System** | macOS 12+ | macOS 26.6.2 (Darwin arm64, Apple M2) | Verified |
| **CPU / GPU** | Apple Silicon (`arm64`) | 8 CPU cores (`arm64`), Metal GPU `Apple M2` | Verified |
| **System Memory** | 8 GiB minimum | 8.00 GiB unified memory | Verified |
| **Available Disk Space** | > 5 GiB | 10.38 GiB free | Verified |
| **Python** | 3.11+ | Python 3.12.6 (`.venv`) | Verified |
| **Speech Engine** | `whisper.cpp` CLI | `whisper.cpp` v1.9.5 (`/opt/homebrew/bin/whisper-cli`) | Verified |
| **Speech Model** | Open-source GGML | `ggml-tiny.en.bin` (74.1 MiB, MIT License) | Verified |
| **Audio Preprocessor** | Local FFmpeg | FFmpeg v7.1 (`/Users/.../.local/bin/ffmpeg`) | Verified |
| **Language Model Engine**| Local Ollama API | Ollama v0.33.3 at `http://127.0.0.1:11434` | Verified |
| **Language Model** | Open-weight Qwen | `qwen2.5:1.5b` (Q4_K_M GGUF, 986 MiB) | Verified |
| **Database** | SQLite3 with WAL, FK & Migrations | SQLite 3.43.2 (`schema_migrations` tracked at version 2) | Verified |

---

## 3. Real Local Integration Workflow Results

The reproducible end-to-end verification script `scripts/smoke_phase_c_integration.py` was executed with synthetic speech generated via macOS `say`:

```text
Story Text: "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop in coastal Maine. Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. He always told me that patience is like trimming the sail: you cannot control the wind, but you can always guide your boat."
```

### Observed Execution Log:

```text
======================================================================
 EchoArchive — Phase C Real Local AI & Traceable Memories Proof
======================================================================

[Step 1/11] Generating synthetic fictional test audio (macOS say)...
  Generated Audio File: phase_c_fictional_test.wav
  File Size:            582.1 KiB

[Step 2/11] Uploading audio with affirmative consent (POST /api/stories)...
  [PASS] Story Created: ID = 76373cdb-b2d4-4a6c-9769-6bf4bffc9305
         Title:         Grandfather's Wooden Sailboat in Maine
         Revision:      0
         Duration:      18.62s

[Step 3/11] Running offline whisper.cpp speech recognition (POST /api/stories/{id}/transcribe)...
  [PASS] Whisper transcription succeeded in 1.26s

[Step 4/11] Retrieving transcript segments (GET /api/stories/{id}/segments)...
  Segments Persisted: 6
    [seg-3249e4251f20] (00.00s -> 05.24s): When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop
    [seg-fe9341a572b4] (05.24s -> 06.68s): in Coastal Main.
    [seg-27a5882b1e10] (06.68s -> 10.82s): Every Sunday morning in July, we took the boat down to the harbor and watched the white
    [seg-fdd381ecfc1b] (10.82s -> 12.28s): sails catch the wind.
    [seg-3ddc1841a15c] (12.28s -> 15.40s): He always told me that patience is like trimming the sail.
    [seg-8e94d5810e94] (15.40s -> 18.56s): You cannot control the wind, but you can always guide your boat.

[Step 5/11] Human review: correcting transcription mistake (PATCH /api/stories/{id}/segments/{seg_id})...
  [PASS] Segment corrected to: 'in coastal Maine.' (Revision 1 -> 2)

[Step 6/11] Extracting grounded memories via local Qwen2.5:1.5b (POST /api/stories/{id}/extract)...
  [PASS] Extraction Job Enqueued: 01b8dedf-ddae-440e-a9fa-414593812cc4
  -> Observed Stage: [RUNNING] extracting
  -> Observed Stage: [SUCCEEDED] succeeded
  [PASS] Qwen memory extraction succeeded in 4.09s

[Step 7/11] Retrieving persisted memory cards via API (GET /api/stories/{id}/cards)...
  [PASS] Retrieved 1 Grounded Memory Card(s):
    Memory Card #1:
      ID:               card-41738b7cb9cb
      Title:            Building a Wooden Sailboat
      Summary:          My grandfather, Arthur, built a small wooden sailboat in his workshop in coastal Maine when I was seven years old. Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. He always told me that patience is like trimming the sail. You cannot control the wind, but you can always guide your boat.
      Themes:           []
      Review State:     draft (Human review required)
      Model Provenance: qwen2.5:1.5b
      Revision:         Rev 2 (is_stale=False)
      Cited Sources:    6 segment(s)
        - [seg-3249e4251f20] (0.00s -> 5.24s): "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop"
        - [seg-fe9341a572b4] (5.24s -> 6.68s): "in coastal Maine."
        - [seg-27a5882b1e10] (6.68s -> 10.82s): "Every Sunday morning in July, we took the boat down to the harbor and watched the white"
        - [seg-fdd381ecfc1b] (10.82s -> 12.28s): "sails catch the wind."
        - [seg-3ddc1841a15c] (12.28s -> 15.40s): "He always told me that patience is like trimming the sail."
        - [seg-8e94d5810e94] (15.40s -> 18.56s): "You cannot control the wind, but you can always guide your boat."

[Step 8/11] Testing source-linked original audio playback (GET /api/stories/{id}/audio with Range)...
  Target Source Moment: [seg-3249e4251f20] 0.00s -> 5.24s
  [PASS] HTTP 206 Seekable audio byte-range stream verified (Content-Range: bytes 0-4095/596056)
  [PASS] Client seeking target: 0.00s -> 5.24s verified available

[Step 9/11] Inspecting card details & updating review state (PATCH /api/cards/{id})...
  [PASS] Card review state transitioned: draft -> accepted

[Step 10/11] Modifying transcript to trigger dynamic STALE card invalidation...
  [PASS] Transcript modified to revision 3
  [PASS] Previously generated card dynamically marked as STALE:
         Reason: Transcript has been modified since generation (card revision 2 vs current revision 3).

[Step 11/11] Regenerating memories against Revision 3 (POST /api/stories/{id}/extract)...
  [PASS] Successfully regenerated 1 card(s) for Revision 3 without duplicates.

======================================================================
 [SUCCESS] EchoArchive Phase C Real Local Integration Verified!
======================================================================
```

---

## 4. Community Wisdom Interlude: Grounding & Citation Integrity

During the design and validation of the server-side evidence validator, developer reports on dev.to were reviewed regarding grounded LLM memory extraction and citation reliability:

- In [*Your AI cited a real file. It still lied to you.*](https://dev.to/enhanciar_ai_96a4ba4877e3/how-we-make-an-llm-cite-every-answer-down-to-fileline-and-check-the-citation-is-telling-the-truth-hmj), researchers demonstrated that merely checking whether an LLM cites existing identifiers does not prevent semantic hallucinations: an LLM can cite a valid document while fabricating the claim itself.
- In [*Bare tokens vs real code: an 11x recall jump in LLM memory verification*](https://dev.to/mansio/your-memory-layer-is-lying-to-you-and-your-llm-agrees-1oia), practitioners found that formatting evidence into real context snippets and validating strict word-level containment prevents false acceptance in memory extraction.

**EchoArchive Architectural Decision:**  
We enforced two strict boundaries based on this community insight:
1. **Never conflate existence with truth:** A memory card is never auto-accepted merely because its segment citations exist. All extracted cards are saved with `review_state = 'draft'` and presented as AI interpretations. The authoritative UI renders the speaker's original transcript text and original audio playback, never the LLM's summary as verbatim speech.
2. **Deterministic quote validation:** Quotations inside memory cards must strictly match the verbatim text of the cited segments (with whitespace/punctuation normalization), rejecting fabricated direct speech with `UNSUPPORTED_QUOTE`.

---

## 5. API Endpoints Contract Implementation

| Method | Endpoint | Status | Description & Payload Contract |
|---|---|---:|---|
| `POST` | `/api/stories/{id}/extract` | 202 | Start grounded memory extraction via local Qwen. Optional body: `{"expected_revision": int}`. Returns `{job_id, story_id, kind: "extract", status: "queued", stage: "queued"}`. Rejects with 422 if no transcript, 409 if revision conflict or job active. |
| `GET` | `/api/stories/{id}/cards` | 200 | List all memory cards for story `id`. Returns `{story_id, current_transcript_revision, total, has_stale_cards, review_status, cards: [...]}`. Each card includes `id`, `title`, `summary`, `themes`, `generated_from_revision`, `is_stale`, `stale_reason`, `review_state`, `model_provenance`, `created_at`, and rich `sources` with seek timestamps. |
| `GET` | `/api/cards/{id}` | 200 | Retrieve a single memory card with its dynamically computed `is_stale` flag and its associated supporting transcript segments. Returns 404 if card not found. |
| `GET` | `/api/cards/{id}/sources` | 200 | Retrieve supporting source transcript segments and audio seek metadata for card `id`. |
| `PATCH` | `/api/cards/{id}` | 200 | Update human review state (`draft`, `accepted`, `dismissed`). Body: `{"review_state": "accepted"}`. Enforces that evidence citations and model provenance cannot be tampered with. |
| `GET` | `/demo`, `/phase-c-demo` | 200 | Serve the Phase C minimal functional playback demonstration harness (`static/phase_c_demo.html`). |

---

## 6. Database Schema & Migration Changes

SQLite schema migration version 2 was added to track model provenance:

```sql
-- Migration 2: Model provenance tracking
ALTER TABLE memory_cards ADD COLUMN model_provenance TEXT NOT NULL DEFAULT 'qwen2.5:1.5b';
```

- **Backward Compatibility:** Default value ensures all Phase B queries and tests continue executing without modification.
- **Relational Invariants:** Foreign key cascading (`ON DELETE CASCADE`) ensures that if a memory card is superseded or a story is deleted, all corresponding `memory_sources` join rows are atomically removed.
- **Atomic Operations:** Card deletion and re-insertion occur within a single SQLite transaction with `PRAGMA busy_timeout = 30000;`.

---

## 7. Test Suite Execution & Coverage Breakdown

Run command: `.venv/bin/pytest -v`

### Summary:
- **Total Tests:** 74
- **Passed:** 74
- **Failed:** 0
- **Duration:** 11.06s

### Test Coverage Breakdown:
1. `tests/test_api.py` (1 test): Health check truthful readiness reporting.
2. `tests/test_cards_api.py` (11 tests) — **New in Phase C**:
   - `test_extraction_from_ineligible_story_without_transcript`: 422 `NO_TRANSCRIPT` for revision 0 stories.
   - `test_extraction_stale_expected_revision_rejected`: 409 `REVISION_CONFLICT` when expected revision mismatches.
   - `test_successful_grounded_memory_extraction_lifecycle`: Verifies `queued` -> `preparing` -> `extracting` -> `validating` -> `saving` -> `succeeded`.
   - `test_extraction_rejects_hallucinated_direct_quote`: Rejects fabricated quotes with `UNSUPPORTED_QUOTE` and rolls back atomically.
   - `test_extraction_rejects_nonexistent_or_cross_story_source_ids`: Rejects invalid IDs with `INVALID_EVIDENCE`.
   - `test_ollama_offline_or_timeout_handling_in_worker`: Proper failure transition for `OLLAMA_UNAVAILABLE` and `OLLAMA_TIMEOUT`.
   - `test_transcript_edit_during_inference_triggers_revision_conflict`: Prevents race conditions when user edits transcript during inference.
   - `test_stale_memory_flag_and_regeneration`: Verifies `is_stale=True` after edit, and clean replacement without duplicates on regeneration.
   - `test_card_details_and_sources_api_endpoints`: Verifies `GET /api/cards/{id}`, sources, and `PATCH /api/cards/{id}` review updates.
   - `test_audio_playback_byte_range_and_timing_safety`: Verifies HTTP 206 Partial Content byte-range streaming for memory playback.
   - `test_phase_c_demo_harness_endpoint`: Verifies `/demo` returns the interactive demonstration HTML harness.
3. `tests/test_corrections.py` (6 tests): Optimistic concurrency control and transcript correction.
4. `tests/test_database.py` (3 tests): Table existence, foreign key enforcement, and cascade deletion.
5. `tests/test_evidence.py` (6 tests): Evidence validation, quote containment, and batch atomicity.
6. `tests/test_extraction.py` (9 tests): Ollama JSON parsing, type validation, and error mapping.
7. `tests/test_ingestion.py` (10 tests): Affirmative consent, bounded streaming, duration limits, and media paths.
8. `tests/test_jobs.py` (6 tests): Background queueing, single worker concurrency, and crash recovery.
9. `tests/test_live_inference.py` (1 test): Live whisper.cpp and Ollama Qwen2.5 memory pipeline on synthetic audio.
10. `tests/test_media.py` (7 tests): Audio decodability, duration checks, and path traversal detection.
11. `tests/test_security_audio.py` (7 tests): Origin/Host filtering, error sanitization, and byte-range streaming.
12. `tests/test_transcription.py` (7 tests): Whisper CLI flags, model detection, and timestamp ordering.

---

## 8. Security & Privacy Audit

- **Loopback Enforcement:** Binds strictly to `127.0.0.1:8766`. Zero telemetry or cloud API requests.
- **Untrusted Model Output:** Output from Qwen is treated as untrusted text: parsed as JSON, strictly validated against title/summary length limits, themes arrays, and exact transcript segment existence before database entry.
- **Subprocess Safety:** External commands (`whisper-cli`, `ffmpeg`) execute with argument lists; `shell=True` is forbidden.
- **Path Traversal & Boundaries:** All audio requests verify containment within `MEDIA_DIR` before file access.
- **Git Hygiene:** SQLite databases (`*.sqlite3`), raw/synthetic user recordings, transcripts, and model weights are strictly gitignored.

---

## 9. Known Deprecations & Limitations

- **Starlette Warning:** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` is tracked as an upstream framework notice and retained without making destabilizing dependency upgrades.
- **Word-Level Synchronization:** Whisper CLI outputs segment-level timestamps; EchoArchive intentionally does not synthesize unverified word-level alignment or frame-perfect karaoke effects.
- **Single Inference Job Concurrency:** By design, local inference concurrency is capped at 1 to prevent exhausting system RAM and GPU resources on laptop hardware.

---

## 10. Recommended Phase D Scope

With Traceable Memories, grounded extraction, and source-linked audio streaming fully operational, Phase D will build the user-facing interface:
- **Archive After Dark Theme:** Palette tokens (`#1B252B`, `#F3E8D6`, `#E5B65F`, `#8C4B4A`) from `docs/UIUX_BRIEF.md`.
- **Six Experiences:** Home/Archive, Audio Recording (browser MediaRecorder with audio level meters), Transcript Review, Memory Extraction Desk, Story Workspace, and Traceable Memory Detail.
- **Interactive Audio Controls:** Waveform scrubber, segment click-to-seek, and visual highlight synchronization.
- **Responsive Layout:** Responsive down to 320px viewport with keyboard navigation and WCAG contrast validation.
