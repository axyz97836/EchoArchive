# EchoArchive — Technical Requirements Document (TRD)

**Status:** Proposed architecture, not an implemented system  
**Primary environment:** macOS laptop; Linux support is conditional on verification  
**Related:** [PRD.md](PRD.md) · [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md) · [APP_FLOW.md](APP_FLOW.md)

## 1. Architectural goals

1. Keep transcription, summarization, storage, and playback local to the user's computer.
2. Make source provenance enforceable by code, not only requested from the language model.
3. Keep the system small enough to inspect and test during the Week 4 challenge.
4. Treat audio and transcription as personal data; avoid invisible uploads or unrequested retention.
5. Make failures recoverable without corrupting prior audio, transcript segments, or memory cards.

## 2. Proposed technology decisions

| Concern | Recommended choice | Rationale / boundary |
|---|---|---|
| UI | HTML, CSS, vanilla JavaScript | Small, self-contained frontend with MediaRecorder and audio playback |
| Local API | Python 3.11+ with FastAPI + Uvicorn | Explicit typed routes and reliable multipart uploads; versions must be pinned and verified |
| Database | SQLite via Python `sqlite3` | Local transactions, relational evidence links, no external service |
| Speech to text | `whisper.cpp` CLI + local model | Open-source offline inference and timestamped segments; inspect installed CLI output and license |
| Audio preparation | FFmpeg as a local tool | Normalize supported formats to 16 kHz mono WAV; use subprocess argument arrays, never shell injection |
| Text extraction | `qwen2.5:1.5b` with Ollama local API | Open-weight LLM for short grounded cards; upgrade/swap only after testing |
| Jobs | One bounded in-process worker with persisted job records | Honest progress for potentially slow local inference; no Redis/Celery |
| Tests | pytest or unittest, plus focused browser smoke tests | Deterministic validation and explicit live-model evidence |
| Packaging | Python venv + pinned dependency manifest | Reproducible laptop setup, no model weights in Git |

These choices are design recommendations. **Phase A must verify** installed whisper.cpp/FFmpeg/Ollama versions and live compatibility before declaring implementation complete.

## 3. Component diagram

```text
Browser (localhost)
 ├─ MediaRecorder / file picker
 ├─ Story workspace + editable transcript
 ├─ Memory cards with verified evidence
 └─ <audio> player, local search, export, delete
             │ HTTP on 127.0.0.1
             ▼
Python API and validators
 ├─ Upload & media validation → private media directory
 ├─ Job controller → SQLite job statuses
 ├─ Transcription adapter → FFmpeg → whisper.cpp + local model
 ├─ Extraction adapter → Ollama (127.0.0.1:11434)
 ├─ Evidence validator → transcript_segments + memory_sources
 ├─ Archive/search/export controller
 └─ SQLite (foreign keys, transactions)
```

## 4. Main processing pipeline

### A. Import and normalize audio

1. Require user-initiated recording or upload plus an affirmative permission acknowledgment.
2. Enforce size limits while receiving data and reject unsupported MIME/extensions or invalid decoded media.
3. Save to a new generated UUID-based filename beneath a private storage root; never trust an uploaded path.
4. Verify decode and duration using a locally installed trusted decoder. Restrict to five minutes for MVP.
5. Normalize a transient working copy to 16 kHz mono WAV if needed. Remove intermediates in `finally` and on startup recovery.
6. Record story metadata in SQLite with a transaction; reconcile failures between filesystem and database.

### B. Transcribe

1. Create a queued `transcribe` job record.
2. Claim the job using a single local worker; store stage transitions (preparing, transcribing, saving).
3. Run whisper.cpp via an argument list (`subprocess.run` or supervised `Popen`, **no `shell=True`**), with a finite timeout.
4. Parse timestamped segments from the tool's supported machine-readable output. **Check the installed CLI's actual flags** rather than assuming a particular version.
5. Enforce chronological `start_ms` / `end_ms`, segment count and text length bounds; reject unusable output.
6. Insert the first transcript revision transactionally, preserving the original audio.
7. If transcription fails, keep the story/audio but show a recoverable failure and allow a retry.

### C. Extract traceable memories

1. Serialize the user's **current transcript revision** into numbered, immutable segment IDs for the request.
2. Ask Ollama's local `/api/chat` endpoint to return structured JSON matching a tight schema, with `stream:false`, an explicitly selected model, and limited output. The API documents JSON/schema-constrained `format` support.
3. Suggested fields: `title`, `summary`, `themes`, `source_segment_ids` (non-empty). **Do not request invented exact quotations or unverified personal facts.**
4. Parse JSON, validate types and length bounds, and verify every cited segment ID belongs to this story and current revision.
5. Reject cards with invalid/missing evidence. Never silently manufacture fallback citations.
6. Persist validated cards with `generated_from_revision` and corresponding `memory_sources` rows.
7. If a transcript changes, increment `transcript_revision` and visually mark older cards stale; regenerating cards requires a deliberate user action.

### D. Replay and inspect sources

1. Display the **actual transcript segment text** as evidence, not an unverified model-created quotation.
2. Offer a play button seeking the browser's audio element to `start_ms / 1000` when valid timestamps exist.
3. Use a bounded same-origin media endpoint supporting byte ranges as needed by browser seeking.
4. Clearly report when precise seeking is unavailable; text provenance still works.

## 5. API guidelines

Canonical endpoints and payloads are defined in [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md). In brief:

- `GET /api/health` readiness for whisper.cpp, FFmpeg, Ollama/model, storage.
- `POST /api/stories` multipart audio + explicit consent/permission acknowledgment.
- `GET /api/stories`, `GET /api/stories/{id}`, `GET /api/stories/{id}/audio`.
- `POST /api/stories/{id}/transcribe` and `/extract`, returning `202 {job_id}`.
- `GET /api/jobs/{job_id}` for real-stage polling, not fake progress.
- `PATCH /api/stories/{id}/segments/{segment_id}` with revision conflict detection.
- `GET /api/stories/{id}/cards`, `GET /api/stories/{id}/export`, `DELETE /api/stories/{id}`.

Errors use consistent `{ "error": { "code": "...", "message": "..." } }` responses without raw local paths or stack traces.

## 6. Runtime and privacy boundaries

- Default bind **only** to `127.0.0.1` on a configurable unused port (suggested `8766` to avoid SlothDesk's `8765`).
- Ollama must be configured for local access; don't connect to hosted model endpoints.
- Apply Origin/Host checks for state-changing requests and reject unexpected cross-origin requests. Do not assume CORS configuration alone stops all CSRF threats.
- Disable framework auto-generated public docs in production if they enlarge attack surface unnecessarily; do not claim this alone is security.
- Validate uploads by content/decodability, not filename alone. Enforce request body, duration, time, output, and job-count limits.
- Store uploaded files outside publicly served frontend assets; map UUID to path through trusted database records, not raw request paths.
- Prevent traversal/symlink escapes and reject external media references. Use exclusive file creation, restrictive permissions where feasible, and atomic replacement for exports/temp files.
- Never commit private `data/`, recordings, SQLite DB, models, transcripts, or generated export ZIPs.
- Treat LLM output as **untrusted data**, not executable instructions; never interpolate it into shell commands or file paths.
- Note clearly: localhost and local files are not encrypted-at-rest or multi-user account security guarantees.
- Check licenses/redistribution requirements for models and tools; do not bundle third-party weights without permission.

## 7. Persistence and concurrency

- One SQLite database with `PRAGMA foreign_keys=ON`, WAL where appropriate, and short transactions.
- Only one heavy inference job executing at a time in the MVP, queued requests with an explicit status.
- Persist job progress by **stage**, not an invented time-based percentage. Jobs interrupted by server restart become `failed` with `INTERRUPTED` at startup; users can retry.
- Story deletion cannot run while an active job writes the story; either block it or cancel/terminate job safely, then delete.
- Export snapshots a consistent database view before packaging audio and text. Avoid including unrelated recordings.
- Filesystem + database operations are not a single atomic transaction: keep reconciliation code, cleanup checks, and tests for partial failures.

## 8. Reliability matrix

| Failure | System response | No-data-loss constraint |
|---|---|---|
| Mic permission denied | Clear notice + manual upload option | No recording created |
| Bad/oversized audio | Validation response before processing | Existing archive unchanged |
| FFmpeg missing | Readiness warning, actionable setup instructions | Original imported audio preserved |
| whisper.cpp/model missing | Job fails with specific code; retry after setup | Original audio preserved |
| Ollama offline | Extraction unavailable; transcript remains | Do not erase prior transcript/cards |
| Invalid structured LLM response | Reject payload, show retry | Do not fabricate cards |
| Card refers to nonexistent segment | Reject that card | Do not invent an evidence link |
| Transcript edited after extraction | Stale-card warning; explicit regeneration | Original raw audio retained |
| Process killed mid-job | Mark interrupted and recover on next start | No false completed state |
| Export fails | No partial download; temporary ZIP removed | Archive unchanged |
| Delete cleanup fails | Report incomplete deletion and retry cleanup | Never falsely claim complete erasure |

## 9. Verification plan

**Automated:** upload limits, media sniff/validation, escaping paths, transcript constraints, stale revision guard, evidence ID validation, job transitions, database cascades, export contents, deletion cleanup, localhost requests, error hygiene. Use synthetic fixtures.

**Live integration:** real short fictional WAV → locally running whisper.cpp model → timestamps → local Qwen via Ollama → source-linked cards → browser seek/audio replay. Record actual tool/model versions and timings.

**Browser:** microphone permission flow, upload fallback, slow inference state, transcript edit/staleness, cards, source replay, search, export, delete, mobile keyboard and reduced-motion.

## 10. Reference documentation

- [whisper.cpp CLI documentation](https://github.com/ggml-org/whisper.cpp/blob/master/examples/cli/README.md) — inspect installed supported output flags and timestamp behavior.
- [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) — local `/api/chat` and schema-constrained outputs.

Document all deviations discovered during Phase A instead of assuming these tools are already installed or tested.
