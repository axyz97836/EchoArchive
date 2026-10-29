---
title: "EchoArchive: Preserving Authentic Spoken Memories with Local Speech & Grounded Open-Weight AI"
published: false
description: "A local-first application preserving real spoken stories through Traceable Memories—where open-weight AI serves as an indexer, not a storyteller."
tags: devchallenge, hf26challenge
---

*This article is submitted for the Hacktoberfest 2026 Week 4 Challenge: Ghost in the Machine (October 26–31, 2026).*

---

## What I Built

**EchoArchive** is a local-first application designed to preserve authentic spoken oral histories and organize them into **Traceable Memories**.

In recent years, generative AI has been increasingly used to "resurrect" deceased loved ones through synthetic voice clones, conversational chatbots, and fabricated memories. These approaches risk distorting genuine human history, inventing biographical facts, and putting unsaid words into real people's mouths.

EchoArchive takes the exact opposite philosophical and architectural approach:

> **The original recording and the human-reviewed transcript are the sole authorities. Local AI serves strictly as an indexing and summarization assistant.**

Every AI-generated memory card in EchoArchive is verifiably grounded in the speaker's actual spoken words. When viewing a memory card, the user can see the authoritative transcript segment and click **"Listen to Spoken Passage"** to seek the audio player to that exact second.

### Core Capabilities

1. **100% Local Inference:** Offline speech recognition via `whisper.cpp` (Metal GPU accelerated) and local language modeling via `qwen2.5:1.5b` through Ollama. Zero telemetry, zero analytics, zero external cloud APIs.
2. **Affirmative Consent by Default:** Explicit affirmative confirmation required before any audio can be recorded or uploaded. No automatic microphone access.
3. **Traceable Memories & Evidence Validator:** Server-side validation rejects any memory card citing non-existent segments, cross-story passages, or hallucinated quotations.
4. **Human Review Authority:** Machine transcripts begin unreviewed. Editing a transcript invalidates prior review status and marks existing cards stale. Memory extraction strictly rejects unreviewed transcripts at the API boundary.
5. **Byte-Range Seekable Playback:** HTTP 206 Partial Content streaming allows users to hear the authentic voice behind every AI summary.
6. **Local Parameterized Search:** 100% offline search across stories, speakers, transcript passages, and memory cards with contextual excerpt snippets.
7. **Portable Air-Gapped Export:** Generates self-contained ZIP archives containing pristine original audio, structured JSON metadata, SHA-256 manifests (`echoarchive-export-v1`), and an offline standalone reader (`story.html`) with zero remote CDNs, fonts, or scripts.
8. **Crash-Safe Deletion Journal:** Deletes stories safely using an atomic SQLite cleanup journal (`deletion_journal`) that reconciles filesystem media purges across power interruptions or worker restarts.

---

## Demo

{% youtube zWXvw_L0HS4 %}

[Watch the EchoArchive Demo](https://youtu.be/zWXvw_L0HS4)

> **Duration:** 3:51.73 | **Resolution:** 1920 × 1080 (30 fps) | **Format:** H.264 / AAC stereo  
> **Narration:** Synthetic local voiceover (macOS `Samantha`, 175 wpm, EBU R128 normalized)  
> **Source Audio Playback:** Authentic fictional recording excerpt audible at 02:01 – 02:09.5  
> **Export Note:** The video captures the genuine in-app ZIP export workflow; the resulting offline standalone `story.html` reader was verified independently with zero remote CDNs.  
> A complete timed narration guide and scene-by-scene script using synthetic fixtures is documented in [`docs/DEMO_GUIDE_AND_SCRIPT.md`](https://github.com/axyz97836/EchoArchive/blob/develop/docs/DEMO_GUIDE_AND_SCRIPT.md).

The complete EchoArchive user journey follows six coordinated screens designed in the archival **Archive After Dark** design system (Midnight Ink `#1B252B`, Aged Parchment `#F3E8D6`, Marigold Amber `#E5B65F`, and Muted Burgundy `#8C4B4A`):

### The 6-Screen Architecture

1. **Home / Entry Screen:** Real-time health monitor displaying local speech engine, audio preprocessor, Ollama, and SQLite storage readiness.
   ![Home Screen](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/01_home_screen.png)

2. **Microphone Studio & Ingest:** Live Web Audio API level metering on an HTML5 canvas, 5-minute duration limit, and affirmative consent confirmation.
   ![Record & Upload Screen](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/02_record_upload_screen.png)

3. **Transcript Review Workspace:** Chronological segments with timestamped audio seeking, inline human error correction, revision increments, and explicit review confirmation.
   ![Transcript Review](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/05_transcript_review_screen.png)

4. **Memory Extraction Stepper:** Real-time background job tracking through truthful stages (`queued` → `analyzing` → `validating` → `saving` → `succeeded`).
   ![Extracting Memories](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/07_extracting_memories.png)

5. **Story Archive Library:** Preserved collection grid with real-time local search and verified memory counts.
   ![Story Archive](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/03_story_archive_screen.png)

6. **Traceable Memory Detail:** Interpretive summaries labeled with theme chips and authoritative spoken passages featuring click-to-seek audio playback.
   ![Memory Detail](https://raw.githubusercontent.com/axyz97836/EchoArchive/main/docs/screenshots/04_memory_detail_screen.png)

*All demo screenshots and automated tests utilize synthetic, fictional test audio fixtures.*

---

## Code

EchoArchive is open-source under the MIT License:

- **Repository:** [https://github.com/axyz97836/EchoArchive](https://github.com/axyz97836/EchoArchive)
- **Active Branch:** `develop`

### Architecture Overview

```text
Browser (http://127.0.0.1:8766)
  │ (HTML5 / Vanilla JavaScript / Web Audio API)
  ▼
FastAPI API Boundary (Loopback: 127.0.0.1:8766)
  ├── Host & Origin Security Middleware (Rejects untrusted external callers)
  ├── Upload Validator ──────> Streaming size limits (25 MiB cap)
  ├── Job Controller   ──────> Single-worker queue with SQLite persistence
  ├── Speech Adapter   ──────> FFmpeg (16 kHz mono) + whisper.cpp (GGML tiny.en)
  ├── Extraction Engine ─────> Local Qwen2.5:1.5b via Ollama (/api/chat)
  ├── Evidence Validator ────> Relational join integrity & quotation verification
  ├── Export Generator ──────> Self-contained ZIP with offline HTML reader
  ├── Deletion Journal ──────> Durable two-phase filesystem/database cleanup
  └── Relational DB    ──────> SQLite3 (PRAGMA foreign_keys = ON, WAL mode)
```

---

## How I Built It

EchoArchive was built from the ground up to solve the core architectural challenges of offline, privacy-preserving AI on modest consumer hardware (Apple Silicon Mac with 8 GiB RAM).

### 1. Offline Speech Recognition Pipeline
- Used `whisper.cpp` (v1.9.5) compiled with Apple Metal GPU acceleration.
- Ingested audio is normalized to 16 kHz mono WAV using local `ffmpeg`.
- A background worker thread executes `whisper-cli` via `subprocess.run` (strictly passing argument arrays, **never `shell=True`**).
- Parses machine-readable JSON output into chronological segments with start/end millisecond timestamps.

### 2. Structured Local Extraction with Qwen2.5
- Employs `qwen2.5:1.5b` running through local Ollama (`http://127.0.0.1:11434`).
- Prompts use structured JSON schemas constraining output to titles, summaries, thematic tags, and non-empty lists of cited segment IDs.
- Execution is strictly bounded with timeouts and validated on receipt.

### 3. Server-Side Evidence Validation (Traceable Memories)
- Because large language models can hallucinate plausible-sounding citations, EchoArchive never trusts the model's claims.
- The `EvidenceValidator` verifies:
  1. Every cited segment ID exists in the database and belongs to the **same story**.
  2. The segment was generated from the **current transcript revision**.
  3. Any direct quotations inside summaries or titles exist verbatim in the source transcript segments.
  4. Cards failing evidence validation are rejected, preventing fabricated claims from ever reaching the user.

### 4. Gated Review Semantics & Optimistic Concurrency
- Machine-generated transcripts begin with `transcript_reviewed_at = NULL`.
- Human corrections (`PATCH /api/stories/{id}/segments/{id}`) increment `transcript_revision` and invalidate review status.
- Memory extraction unconditionally rejects unreviewed transcripts (`422 REVIEW_REQUIRED`).
- If an API caller attempts to bypass review (`require_review: false`), the backend returns `422 REVIEW_BYPASS_FORBIDDEN`.
- When a user corrects a transcript after memories were already extracted, older cards are marked stale and blocked from acceptance until re-reviewed and regenerated.

### 5. Durable Crash-Safe Deletion
- SQLite transactions cannot atomically include arbitrary filesystem `unlink` operations.
- To prevent orphaned media files if a server crashes mid-deletion, EchoArchive implements a durable cleanup journal:
  1. Deletion requests acquire a per-story worker lock and verify no jobs are active (`409 JOB_ACTIVE`).
  2. Inside a single SQLite transaction, the files to be purged are recorded in `deletion_journal` and the story row is deleted (cascading foreign keys remove segments and cards).
  3. Filesystem audio, transcripts, and temporary files are unlinked.
  4. If all unlinks succeed, the journal row is cleared.
  5. If an interruption or power loss occurs, `recover_pending_deletions()` runs at startup to safely purge remnant files.

### 6. Portable Self-Contained ZIP Export
- Produces a user-owned ZIP file containing:
  - Original, unmodified audio bytes
  - `story.json`, `transcript.json`, and `memories.json`
  - `manifest.json` with SHA-256 member checksums (`echoarchive-export-v1`)
  - `story.html`: a standalone, responsive reader with inline CSS that plays the audio via relative path without remote CDNs, web fonts, or scripts.

### 7. Lessons Learned: Security Hardening, Review Bypasses & CI Integrity

During Phase F hardening and pre-release audits, several subtle architectural vulnerabilities and engineering lessons emerged:
1. **The Review Bypass Trap:** A pre-flight audit revealed that `POST /api/stories/{id}/extract` accepted an optional `require_review: bool = false` flag in its schema. While intended for internal automated testing, exposing this parameter on public API endpoints created a loophole where callers could bypass human review. We eliminated this vulnerability by strictly requiring `transcript_reviewed_at IS NOT NULL` at the backend domain boundary, rejecting any bypass attempts with `422 REVIEW_BYPASS_FORBIDDEN`.
2. **Filesystem vs. Database Atomicity:** In relational databases, rolling back a transaction cannot undo a deleted file on disk. Introducing the staged `deletion_journal` ensured that crash recovery can resume pending deletions cleanly on startup without leaving orphaned audio files or corrupting referential integrity.
3. **CI Runner Isolation & Mocking:** GitHub Actions virtual environments lack Apple Metal hardware acceleration and GPU access. Establishing isolated synthetic audio fixtures, mocking subprocess executions with deterministic outputs in automated test harnesses, and tuning single-worker polling intervals allowed 115 deterministic unit and integration tests to execute in under 2 seconds in GitHub Actions CI, while live local speech recognition (`whisper.cpp`) and Ollama Qwen 2.5 extraction run on localhost.
4. **Authentic Demonstration Verification:** Rather than relying on simulated mockups, the complete end-to-end workflow was recorded live via headless browser automation driving real inference on localhost, ensuring that every timestamp, UI transition, and model output reflected true runtime behavior.

---

## Why Does Open Innovation Matter?

Open innovation—grounded in open-weight models, open-source runtimes, and local execution—is essential for personal memory preservation for three fundamental reasons:

1. **Data Sovereignty and Intimacy:** Personal stories and family voices are among the most intimate data a human being produces. Requiring people to stream private recordings to proprietary cloud APIs risks surveillance, model training on private voices, and sudden loss of access when a commercial service shuts down or changes its terms.
2. **Longevity and Archival Durability:** Proprietary cloud services come and go. Open-weight models (like Qwen) and open-source tools (like `whisper.cpp`, `ffmpeg`, and SQLite) can be archived, compiled, and executed decades into the future on independent hardware without reliance on external servers.
3. **Auditability and Truth:** Proprietary AI systems operate as black boxes, hiding system prompts and hallucination rates behind closed APIs. Open-source architectures permit full inspection: every prompt, every schema, and every evidence validation check is verifiable by the user and the community.

---

## The Spirit of It

The theme of Hacktoberfest 2026 Week 4 is **Ghost in the Machine**.

Many contemporary AI applications interpret this theme by creating synthetic ghosts: training voice clones to mimic deceased relatives, generating conversational avatars that pretend to possess the memories of people who have died, or inventing fictionalized family trees.

EchoArchive offers an alternative interpretation:

> **The real ghost in the machine is the authentic human voice that was actually recorded.**

When a person speaks, the nuances of their breathing, hesitation, timbre, and regional accent carry profound emotional and historical weight. A language model should not invent what they might have said or mimic how they might have sounded.

In EchoArchive, the machine's role is not to replace the human, but to serve as a faithful, humble archivist: transcribing the voice, accepting human corrections, organizing thematic memories, and always keeping the listener exactly one click away from the authentic, living recording.

---

## AI-Assisted Development & Media Disclosures

In accordance with DEV community standards and Hacktoberfest AI disclosure guidelines:
- **Core Design & Human Consent:** EchoArchive is architected to preserve authentic, original recordings from consenting human speakers. The application rejects voice cloning, deepfake synthesis, and resurrective persona generation.
- **Fictional Test Fixtures:** All demonstration audio files (*Aunt Clara's Maple Sugar Cabin* and *Echoes of the Ancient Olive Grove*) are 100% fictional synthetic recordings created strictly for software verification and demonstration, containing zero private, personal, or real-world family recordings.
- **Automated Video Demonstration:** Demonstration video interactions were driven via headless Chromium automation (Playwright) operating against the live local application stack. All speech recognition (`whisper.cpp`) and memory extraction (Qwen 2.5) during the recorded run were executed live on localhost.
- **Synthetic Voiceover:** Demonstration video narration was generated offline using macOS local speech synthesis (`Samantha`, `en_US` at 175 wpm) and normalized via FFmpeg EBU R128 loudness filtering. No human voice was mimicked or cloned.
- **Export & Reader Verification:** The demonstration video captures the in-app portable ZIP export workflow; the extracted standalone offline `story.html` reader was verified independently in a separate test pass.
- **AI Interpretations & Evidence Validation:** Extracted memory summaries and thematic tags represent machine interpretations generated by `qwen2.5:1.5b`. While EchoArchive's server-side Evidence Validator cryptographically guarantees that segment citations belong to the same story revision and quotations are verbatim, automated validation cannot guarantee that conceptual summaries are factually flawless or complete. Human review remains the ultimate authority.
- **Code & Architecture Assistance:** EchoArchive was developed through agentic pair programming with Google DeepMind's Antigravity assistant, which assisted in architectural formulation, SQLite schema and migration design, FastAPI route implementation, evidence validation logic, test suite authoring, and documentation. All code, database schemas, and cryptographic checksums were verified via 116 automated local tests (115 deterministic unit and integration tests executing in under 2 seconds in CI plus genuine live local inference validation) with a 100% pass rate.

---

## Verified Engineering Limitations

To maintain honesty and technical integrity:

1. **Local Storage Encryption:** Stored audio recordings in `data/media/` and SQLite databases reside as unencrypted local files on the host filesystem. Device-level encryption (e.g., Apple FileVault or Linux LUKS) is required for encryption-at-rest. Localhost binding does not substitute for multi-user operating system boundaries.
2. **SSD Physical Wear-Leveling:** File deletion unlinks filesystem pointers and removes database rows. On modern SSDs, underlying flash memory blocks are managed by hardware wear-leveling controllers and do not constitute certified cryptographic forensic erasure.
3. **Sequential Job Concurrency:** Inference jobs are bounded by a single background worker (concurrency = 1) to prevent memory contention on 8 GiB RAM laptop environments.
4. **Target Environment:** Verified on macOS 26.6.2 (Darwin arm64, Apple M2, 8 GiB RAM). Linux and Windows deployments require separate validation of whisper-cli and FFmpeg binary paths.
5. **AI Interpretation Boundaries:** Language model extraction provides an organizing aid, not an infallible historical record. Users should always consult the original recorded audio and human-verified transcript as primary sources.
