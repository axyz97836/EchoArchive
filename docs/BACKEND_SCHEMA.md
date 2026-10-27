# EchoArchive — Backend Schema & API Contracts

**Status:** Proposed, version 0.1 schema. Create migrations/tests before implementation.  
**Storage:** SQLite + private local media directory  
**Companion:** [TRD.md](TRD.md) · [PRD.md](PRD.md) · [APP_FLOW.md](APP_FLOW.md)

## 1. Logical data relationships

```text
stories (1) ──< transcript_segments
    │
    ├──< memory_cards (1) ──< memory_sources >── transcript_segments
    │
    └──< jobs

Private media: data/media/{uuid}.{validated_ext}
SQLite:        data/echoarchive.sqlite3
Exports:       produced on demand, not retained by default
```

Each memory card belongs to one story and cites segments from the **same** story. Database foreign keys enforce existence; application code must enforce cross-story identity and current transcript revision.

## 2. SQLite DDL (proposed first migration)

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE stories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
    speaker_label TEXT,
    consent_confirmed_at TEXT NOT NULL,
    audio_relpath TEXT NOT NULL UNIQUE,
    audio_media_type TEXT NOT NULL,
    audio_size_bytes INTEGER NOT NULL CHECK(audio_size_bytes > 0),
    audio_duration_ms INTEGER,
    transcript_revision INTEGER NOT NULL DEFAULT 0
        CHECK(transcript_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE transcript_segments (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL CHECK(segment_index >= 0),
    start_ms INTEGER NOT NULL CHECK(start_ms >= 0),
    end_ms INTEGER NOT NULL CHECK(end_ms > start_ms),
    text TEXT NOT NULL CHECK(length(trim(text)) > 0),
    user_edited INTEGER NOT NULL DEFAULT 0 CHECK(user_edited IN (0,1)),
    UNIQUE (story_id, segment_index)
);

CREATE TABLE memory_cards (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
    summary TEXT NOT NULL CHECK(length(summary) BETWEEN 1 AND 2000),
    themes_json TEXT NOT NULL DEFAULT '[]',
    generated_from_revision INTEGER NOT NULL CHECK(generated_from_revision >= 1),
    review_state TEXT NOT NULL DEFAULT 'draft'
        CHECK(review_state IN ('draft','accepted','dismissed')),
    created_at TEXT NOT NULL
);

CREATE TABLE memory_sources (
    card_id TEXT NOT NULL REFERENCES memory_cards(id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    PRIMARY KEY (card_id, segment_id)
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('transcribe','extract')),
    status TEXT NOT NULL CHECK(status IN
        ('queued','running','succeeded','failed')),
    stage TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX ix_segments_story_order
    ON transcript_segments(story_id, segment_index);
CREATE INDEX ix_cards_story ON memory_cards(story_id);
CREATE INDEX ix_jobs_story ON jobs(story_id, created_at);
```

### Schema invariants and caveats

- IDs are server-generated UUIDs; never derive filesystem paths from story titles or uploaded filenames.
- Timestamp strings use ISO 8601 UTC with timezone information.
- `consent_confirmed_at` records **the user's assertion** of permission, not independently verified consent.
- Transcript is not populated until transcription succeeds; first successful transcript sets `transcript_revision=1`. User edits increase the revision.
- The schema stores edited transcript text; retaining the **original machine-generated transcript** separately is required for auditability. Minimal strategy: immutable `data/original_transcripts/{story_id}.json` created only on first transcription, excluded from Git and included in export. A later schema migration may normalize this.
- Application must validate `memory_sources` join pairs belong to the same story before insertion. A cross-story source is invalid even if both IDs exist.
- `generated_from_revision != stories.transcript_revision` means a card is stale and needs review/regeneration.
- Themes are a validated bounded JSON string array; schema alone does not enforce JSON validity across all SQLite builds.
- Keep original audio immutable once ingested; clean up and reconcile media/SQLite on partial failures.
- SQLite does not enforce that every card has a source. The extraction transaction must insert card + at least one valid evidence row atomically, and read paths must reject orphaned cards.
- Audio duration is populated only after media inspection; reject recordings over the configured duration limit.

## 3. Private storage layout

```text
data/                              # gitignored entirely
├── echoarchive.sqlite3
├── media/
│   └── <story_uuid>.<allowed_extension>
├── original_transcripts/
│   └── <story_uuid>.json
└── tmp/
    └── <random_uuid>...           # cleaned on failure/startup
```

Use permissions appropriate to the current local OS and strict path containment. A `.gitkeep` may be tracked instead of private content.

## 4. API contract conventions

- Base: `http://127.0.0.1:8766` (configurable; never expose to `0.0.0.0` by default).
- All POST/PATCH/DELETE endpoints reject untrusted Origins/Hosts. Bind to loopback and restrict CORS; do not confuse CORS with comprehensive CSRF protection.
- Return JSON except for audio/download endpoints. IDs are strings; timestamps are ISO UTC.
- Errors: `{ "error": { "code": "OLLAMA_UNAVAILABLE", "message": "Ollama is not running locally." } }`.
- Never return raw stack traces, shell commands assembled from untrusted input, or private absolute paths.
- `202` = asynchronous job accepted, `409` = revision or state conflict, `413` = too large, `415` = unsupported format, `422` = malformed request.

## 5. Planned endpoints

| Method | Route | Request / outcome |
|---|---|---|
| GET | `/api/health` | `{api, ollama, transcription, model, ffmpeg, storage}` with truthful ready/missing states |
| POST | `/api/stories` | `multipart/form-data`: `audio`, `title`, optional `speaker_label`, `permission_confirmed=true`; return `201 {id}` |
| GET | `/api/stories` | Paginated list; `?q=` local search, normalized and length-limited |
| GET | `/api/stories/{id}` | Metadata, revision, current job summary |
| GET | `/api/stories/{id}/audio` | Authenticated-by-local-boundary media access; seekable byte-range stream; no arbitrary path input |
| POST | `/api/stories/{id}/transcribe` | Start or retry transcription; `202 {job_id}`, `409` if incompatible active job |
| GET | `/api/stories/{id}/segments` | Ordered segments, current revision, timestamps |
| PATCH | `/api/stories/{id}/segments/{segment_id}` | `{text, expected_revision}`; atomically update and increment revision; `409` on stale edit |
| POST | `/api/stories/{id}/extract` | Start grounded Qwen extraction; requires transcript; `202 {job_id}` |
| GET | `/api/stories/{id}/cards` | Source-linked cards with computed `stale` flag |
| PATCH | `/api/cards/{id}` | Change review state (draft/accepted/dismissed), no fabricated provenance |
| GET | `/api/jobs/{job_id}` | Job kind, status, truthful stage, sanitized error, timestamps |
| GET | `/api/stories/{id}/export` | ZIP with original audio, transcript JSON/text, memory cards and source IDs |
| DELETE | `/api/stories/{id}` | Explicitly confirmed in UI; remove user-owned story and derivatives; handle cleanup failures |

**Keep endpoints minimal.** A partial functional MVP with truthful status is preferred over dummy implementations of every route.

## 6. Example: processing job response

```json
{
  "job_id": "e347c963-9fda-4f67-a392-caa089e7f3a5",
  "story_id": "81da4fef-d71b-4b28-b11f-9814a49d0952",
  "kind": "transcribe",
  "status": "running",
  "stage": "transcribing",
  "error": null
}
```

Stage transitions must reflect actual work; the frontend should display `Transcribing audio...` rather than fake percentage progress if the engine cannot report meaningful progress.

## 7. Example: grounded memory extraction

Input transcript segments (fictional):

```json
[
  {"id":"seg-001","start_ms":1200,"end_ms":5400,"text":"When I was young, we planted marigolds by the courtyard."},
  {"id":"seg-002","start_ms":5400,"end_ms":9700,"text":"Every autumn my grandmother showed me which flowers to save."}
]
```

Expected **proposed** model output:

```json
{
  "cards": [
    {
      "title": "Marigolds in the courtyard",
      "summary": "The speaker remembers planting marigolds and learning from their grandmother.",
      "themes": ["gardening", "family tradition"],
      "source_segment_ids": ["seg-001", "seg-002"]
    }
  ]
}
```

This is an **illustrative fixture, not a claim that the model already produced these words**. Server validation must resolve IDs against the current story. The UI renders actual segment text from SQLite as its citations, never a fabricated LLM quotation.

## 8. Searching, export and deletion

- **Search:** Start with bounded indexed story-title matching plus `LIKE` over transcript/card text; evaluate SQLite FTS5 only if available and tests justify it. Escape wildcard literals where appropriate.
- **Export:** Create ZIP on demand. Include `story.json`, `transcript.json`, `memory_cards.json`, `original_audio.<ext>`, and optional `transcript.txt`. Validate archive entry names (ZIP slip prevention).
- **Delete:** UI requires confirmation. Reject while a job is actively modifying that story, or coordinate safe cancellation. Remove SQLite rows and original audio/transcript derivatives. Because SQLite and filesystem aren't one transaction, implement reconciliation and report incomplete cleanup; do not promise irrecoverable secure erasure.

## 9. Error and validation contract

| Code | Suggested HTTP | UI action |
|---|---:|---|
| `CONSENT_REQUIRED` | 422 | Confirm permission to record or upload |
| `AUDIO_TOO_LARGE` | 413 | Use shorter audio, up to 25 MiB |
| `UNSUPPORTED_AUDIO` | 415 | Try WAV/MP3/M4A/WebM supported by installed FFmpeg |
| `AUDIO_TOO_LONG` | 422 | Trim to at most five minutes |
| `TRANSCRIBER_UNAVAILABLE` | 503 | Install/check whisper.cpp + model |
| `FFMPEG_UNAVAILABLE` | 503 | Install/configure local FFmpeg |
| `OLLAMA_UNAVAILABLE` | 503 | Start Ollama and confirm Qwen model availability |
| `INVALID_AI_OUTPUT` | 502 | Retry extraction; transcript stays saved |
| `INVALID_EVIDENCE` | 422 | Regenerate card; no unsupported citation shown |
| `REVISION_CONFLICT` | 409 | Reload latest transcript before editing |
| `JOB_ACTIVE` | 409 | Finish current processing before a conflicting action |
| `DELETE_INCOMPLETE` | 500 | Explicitly disclose remaining data and recovery path |

## 10. Test obligations

Write DB and API tests for foreign keys, cross-story evidence IDs, card-without-evidence rejection, stale revisions, update conflicts, unsupported upload formats, invalid audio, input limits, interrupted jobs, export integrity, deletion, and error hygiene. Include a separate live integration test for the complete transcription→Qwen→source playback flow with fictional data.
