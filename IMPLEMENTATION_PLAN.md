# EchoArchive — Engineering Implementation Plan

**Hacktoberfest Week 4:** October 26–31, 2026  
**Project:** EchoArchive — Stories fade. Their voices don't have to.  
**Status:** Proposed phases and quality gates, not a completion report  
**Workflow:** Local, verified checkpoints; no automatic remote push or public submission

## 1. Delivery principle

Prove that **two different kinds of local AI** can work together before spending time on visual polish:

1. whisper.cpp produces usable, timed transcript segments from **real fictional test audio**.
2. Qwen via Ollama creates structured memory cards from those segments.
3. Server validation confirms that the card's source IDs actually exist and belong to the correct story.
4. Clicking a source can find and replay the original recording.

If this proof fails, cut scope or resolve the prerequisite. Do not fabricate results or build a demo around mocked inference.

## 2. Dependency graph

```text
A. Foundation + real AI proof
          │
          ▼
B. Local audio ingest + transcript storage
          │
          ▼
C. Evidence-linked memory cards + audio seeking
          │
          ▼
D. Premium archive UI + recording flow
          │
          ▼
E. Search/export/delete + accessibility/privacy
          │
          ▼
F. Full verification, GitHub release, DEV submission
```

Work on a **new repository**; do not change SlothDesk or SentinelAI while building EchoArchive.

## 3. Phase A — Repo, feasibility and minimum real AI proof

**Goal:** Demonstrate the actual offline transcription-to-extraction path with fictional data.

**Tasks**

- Confirm date/repo eligibility from the official Week 4 rules and record repository creation time accurately.
- Inspect Python version/architecture, CPU/RAM/storage, FFmpeg, whisper.cpp binary + installed speech model, Ollama + installed Qwen model.
- Verify current licensing and command-line formats; document exact versions, commands, and provenance of weights.
- Create minimal project layout, `.gitignore`, MIT license if chosen with valid author attribution, dependency manifests, and README setup.
- Make a 20–60 second **fictional** WAV fixture using consenting/synthetic material; no private interview recordings.
- Run local whisper.cpp inference and parse timed segments; store raw output as a sanitized test artifact if safe.
- Send the resulting transcript to local Qwen with a strict JSON schema; validate card fields and segment IDs.
- Implement at least one check proving invalid/missing evidence is rejected.
- Add deterministic unit tests with mocked external processes and a separate real-inference smoke command.
- Commit locally after verification. **Do not push or proceed without review.**

**Exit gate:** Both real models run at least once in the actual target environment; output is inspectable; errors and timings recorded. If not, stop with a dependency gap report.

## 4. Phase B — Safe audio capture/import and persistence

**Goal:** A story can be recorded or uploaded locally and transcribed into durable editable segments.

**Tasks**

- Implement FastAPI endpoints for upload, health, story listing/details, transcription initiation and jobs.
- Enforce explicit permission acknowledgement, size (25 MiB), duration (5 minutes), media decode validation, safe generated filenames and contained paths.
- Support browser MediaRecorder when available and file-picker fallback. Normalize to WAV locally with FFmpeg as needed.
- Build SQLite migration and referentially valid story/segment/job persistence with `PRAGMA foreign_keys=ON`.
- Implement single-job local worker, truthful stage polling, bounded timeouts and recovery of interrupted jobs.
- Preserve original audio and immutable initial recognition result. Edits increment transcript revision.
- Unit + integration tests for bad input, failed tools, timeout, restart recovery and transcript edits.
- Commit verified changes locally; no push.

**Exit gate:** Real audio upload → transcription → editable stored segment list; crash/error does not delete original audio.

## 5. Phase C — Qwen memory extraction and Traceable Memories

**Goal:** Every AI-produced card is explicitly grounded in actual transcript segments.

**Tasks**

- Build schema-constrained local Ollama extraction and strict server-side validation.
- Require ≥1 valid same-story segment ID per card, bounded text/tags, no invented direct quotes.
- Persist cards and `memory_sources` in the same transaction.
- Implement correct transcript revision checks and stale-card warnings after edits.
- Implement audio serving/seek, source segment highlighting, and accessible "Hear original" controls.
- Demonstrate two real cards linked to test-audio moments; verify timestamps empirically.
- Test invalid/cross-story citations, stale races, malformed JSON, Ollama offline and playback seek fallback.
- Commit locally after browser + backend verification.

**Exit gate:** A card opens real segment evidence and seeks the correct original audio region when available, not just a model-generated summary.

## 6. Phase D — Archive After Dark frontend

**Goal:** A visually memorable, functional archive rather than a generic SaaS dashboard.

**Tasks**

- Implement the approved palette and design tokens from [UIUX_BRIEF.md](UIUX_BRIEF.md).
- Build home/archive, new story (record/upload), story workspace, transcript editor, memory cards and diagnostics.
- Create real responsive desktop/mobile layouts with intentional typography and source-first hierarchy.
- Implement loading, error, disabled, recording and transcription states without false progress.
- Add restrained waveform animation only if driven by real recording state; reduced-motion fallback.
- Browser verification at 320/375/768/1024/1280/1440px, including long titles and keyboard navigation.
- Check all visible controls; don't introduce placeholder buttons.
- Commit verified frontend work locally.

**Exit gate:** One person can perform the full source-linked journey on a laptop, including microphone-denied fallback, without reading developer instructions.

## 7. Phase E — Archive quality, export, deletion, accessibility

**Goal:** Make EchoArchive genuinely useful and respectful of personal stories.

**Tasks**

- Add real local search across titles/transcripts/card content; verify no external requests.
- Export a story ZIP containing original audio, transcript and referenced AI memory data. Validate ZIP paths/contents.
- Delete with explicit confirmation and coordinated job state; test DB cascade + media cleanup and partial failure reporting.
- Clear errors, setup instructions and exact local privacy limitations.
- Complete keyboard, focus, dialog, aria-live, contrast and reduced-motion review; test both themes if present.
- Add tests for search, export, deletion, orphan cleanup and interrupted jobs.
- Commit verified changes locally.

**Exit gate:** A user can find, export and remove their own data; essential privacy and error states work in the browser.

## 8. Phase F — End-to-end verification, repository and submission

**Goal:** Publish a reproducible open-source project with a true demonstration.

**Engineering verification**

- Run full Python tests, lint/type checks if configured, and browser smoke tests.
- Run real whisper.cpp + Ollama inference with 2–3 distinct fictional audio samples.
- Verify a full record/import → transcript/edit → extract → source playback → search → export/delete round-trip.
- Test on the actual supported OS and note differences in any other OS, without overstating compatibility.
- Review upload, symlink, path traversal, localhost origin, cross-story evidence, stale revision and deletion race cases.
- Confirm no personal recordings/SQLite files, model weights, secrets, caches, or agent workspace paths are tracked.
- Verify all source files have proper license/attribution.
- Run CI on a reviewable GitHub PR once an explicit remote push is approved; don't merge failed checks.

**Release and submission**

- Write README (prerequisites, model downloads, safe setup, demo steps, limitations), CONTRIBUTING and SECURITY docs.
- Capture genuine application screenshots and a video showing the original recording replay from an AI card.
- Prepare DEV article using the official Week 4 template: What I Built, Demo, Code, How I Built It, Why Open Innovation Matters. Include The Spirit of It only if a genuine result exists; Agent Session and Prize Categories only when applicable.
- Explain AI-assisted development transparently and distinguish measured data from aspirational claims.
- Verify challenge eligibility and publication cutoff from the **live official page** before submission.
- Require separate user approval for GitHub push, merge, tag/release and DEV publication.

**Exit gate:** Real media demo, passing test suite/CI, correct links and publication-ready copy, no private data in Git.

## 9. Quality and security gate checklist

A phase is never called complete merely because an agent says it is. Require:

- [ ] `git status` captured; no unrelated changes or secrets.
- [ ] Actual files/diff inspected.
- [ ] Focused and regression tests pass.
- [ ] An actual browser workflow was observed where applicable.
- [ ] Local-model claims backed by logs or console output from real inference.
- [ ] No silent weakening of limits, validation, consent, deletion, or provenance rules.
- [ ] README and phase evidence updated.
- [ ] Commit is a traceable local checkpoint.
- [ ] Remote push/merge only when separately authorized.

## 10. Suggested repository layout

```text
EchoArchive/
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml                 # pinned dependencies / tooling
├── APP_FLOW.md
├── BACKEND_SCHEMA.md
├── IMPLEMENTATION_PLAN.md
├── PRD.md
├── TRD.md
├── UIUX_BRIEF.md
├── backend/
│   ├── main.py                   # API assembly
│   ├── config.py                 # localhost, model, limits, paths
│   ├── database.py               # SQLite + migrations
│   ├── media.py                  # safe ingest, validation, FFmpeg
│   ├── transcription.py          # whisper.cpp adapter
│   ├── extraction.py             # Ollama + schema validation
│   ├── jobs.py                   # bounded work queue
│   ├── archive.py                # search/export/delete
│   └── evidence.py               # source validation
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/
│   ├── test_database.py
│   ├── test_api.py
│   ├── test_audio.py
│   ├── test_evidence.py
│   ├── test_archive.py
│   └── fixtures/                 # fictional-only generated assets
├── scripts/
│   ├── check_local_models.py
│   └── smoke_real_inference.py
└── data/                         # gitignored, created at runtime
```

This is a **target**, not an assertion that these files already exist. Defer modules until their phase requires them.

## 11. Risks and fallback options

| Risk | Severity | Contingency |
|---|---|---|
| whisper.cpp / model installation unavailable | Blocker | Stop Phase A; document exact dependency path or use verified local alternative |
| Speech timestamps inaccurate | High | Ground citations in segments; label playback timestamps approximate; never fake word alignment |
| Small Qwen invents biographical details | High | Schema + evidence ID validation + transcript-first UI + human review |
| Slow local inference | Medium | One job at a time, truthful stage feedback; shorter fictional demo clip |
| Browser mic unsupported | Medium | Upload WAV as baseline, optional MediaRecorder when available |
| Incomplete delete across SQLite/filesystem | High | Reconciliation and explicit user-facing failure; never claim deletion succeeded if files remain |
| Privacy overselling | High | No claim of encryption, multiuser security, or verified Windows support without implementation evidence |
| Time pressure before Oct 31 | High | Prioritize Phase A/C provenance and a demonstrable safe import→card→audio flow over polish |

## 12. Next action

Start **Phase A only**, create a new workspace and Git repository with these six design documents at its root, verify the local AI prerequisites, and prove real local speech-to-text + Qwen extraction with a fictional audio fixture. Stop at any unapproved install, critical compatibility failure or security gate, report evidence, and seek review before Phase B.

**Companion docs:** [PRD.md](PRD.md), [TRD.md](TRD.md), [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md), [APP_FLOW.md](APP_FLOW.md), [UIUX_BRIEF.md](UIUX_BRIEF.md).
