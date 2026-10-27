# EchoArchive — Product Requirements Document (PRD)

**Project:** EchoArchive  
**Tagline:** Stories fade. Their voices don't have to.  
**Challenge:** Hacktoberfest 2026, Week 4 — Ghost in the Machine (October 26–31, 2026)  
**Status:** Proposed product specification; implementation and results are **not** yet verified  
**Scope:** Local-first, single-user MVP for macOS; other platforms require separate verification

> EchoArchive preserves **real** spoken memories. It does not impersonate people, invent recollections, or present AI interpretations as authentic quotations.

## 1. Product summary

EchoArchive lets someone record or import a short spoken story, transcribe it on their own computer, review the transcript, and create evidence-linked memory cards using an open-weight language model. Each card points back to the transcript segments and corresponding original audio. The archive is searchable, exportable, and deletable by its owner.

The product's central idea is **Traceable Memories**: every AI-created memory card must lead back to what the person actually said. The speaker's recording is the source of truth; AI acts as an organizer, not as a storyteller claiming personal knowledge.

## 2. Why this exists

Personal recordings often become forgotten files with names such as `recording_014.m4a`. They can be hard to search or share thoughtfully. Hosted transcription and summarization tools may require uploading deeply personal voices and family stories. EchoArchive makes it possible to create a meaningful archive **without requiring a cloud inference service**.

### Audience

| Audience | Need | MVP support |
|---|---|---|
| Student or hobbyist oral historian | Save an interview and find key moments later | Capture/upload, transcript, memory cards, search |
| Family member (with permission) | Preserve a relative's actual story and voice | Consent reminder, source-linked cards, audio replay |
| Local-history volunteer | Maintain a small private collection of interviews | Multiple stories, search, individual export |

**Not targeted in the MVP:** medical records, legal evidence management, shared family accounts, professional archival compliance, or interviews without the speaker's permission.

## 3. Goals and measurable acceptance criteria

1. **Real local AI:** At least one short **synthetic** audio sample is transcribed by a real local speech-recognition engine and processed by a real local language model during verification. Never represent mocked tests as proof of live inference.
2. **Human-correctable transcription:** A user can inspect and edit segment text without editing the underlying audio. The UI shows whether cards need regeneration after transcript changes.
3. **Grounded cards:** Every generated memory card has at least one validated transcript-segment source reference. Unsupported assertions are rejected or labeled for review.
4. **Audio traceability:** Selecting a card's source navigates to the corresponding timestamp of the original recording when reliable timestamps exist. When they don't, show text evidence and state the limitation.
5. **User-owned data:** Stories live in local storage, with an export and a deletion flow. No telemetry or mandatory hosted APIs.
6. **Usable demo:** A judge can watch a real, reproducible flow: import fictional audio → transcribe → review → extract → click source → hear audio → export/delete.
7. **Reliability:** Deterministic automated tests cover validation, persistence, provenance, errors, and deletion; the full local AI path has separately reported live evidence.

These are **proposed acceptance gates**, not claims that the project already meets them.

## 4. MVP requirements

| ID | Priority | Requirement | Acceptance criteria |
|---|---|---|---|
| FR-01 | Must | Explicit recording/upload consent | No microphone access before a user action; user confirms permission to record/use audio before import |
| FR-02 | Must | Record or upload audio | Browser microphone recording when supported; uploaded WAV/MP3/M4A/WebM accepted only after validation |
| FR-03 | Must | Safe local ingestion | File type and decoded audio validated; bounded size and duration; generated storage IDs prevent path traversal |
| FR-04 | Must | Local transcription | whisper.cpp (or documented equivalent) processes audio locally; segments retain text and timestamps if available |
| FR-05 | Must | Transcript correction | Editable segments, saved safely; revision increments and stale AI cards are visibly marked |
| FR-06 | Must | Local memory extraction | Qwen2.5 via Ollama generates schema-validated titles, summaries, themes, and source-segment IDs |
| FR-07 | Must | Evidence-first cards | Cards link to transcript text; timestamped segments allow replay of original audio |
| FR-08 | Must | Personal archive | List stories, view metadata, open a story and its memory cards |
| FR-09 | Must | Search | Search titles/transcript/card text locally; show matches and open associated story |
| FR-10 | Must | Export | Produce user-owned ZIP containing original audio, transcript JSON/text and source-linked cards |
| FR-11 | Must | Delete | Confirm deletion and remove database references and owned audio/derivatives; report partial cleanup failures |
| FR-12 | Must | Processing feedback | Honest queued/running/completed/failed states; no fabricated percentages |
| FR-13 | Must | Privacy by default | Bind to loopback only; no external inference requests or analytics; no private recordings in Git |
| FR-14 | Should | In-product source playback | Play from valid start timestamp, with a readable fallback if seeking is unsupported |
| FR-15 | Should | Responsive accessible UI | Keyboard-accessible controls, visible focus, understandable errors, reduced motion, 320px+ viewport support |
| FR-16 | Could | Multiple speakers/languages | Defer until accuracy and consent requirements are demonstrated |

### MVP input limits (initial policy, adjust only with evidence)

- Maximum uploaded file: **25 MiB**.
- Maximum decoded duration: **5 minutes**.
- One transcription/extraction job at a time in the first release.
- Primary test language: **English**. Other languages are best-effort and must not be advertised as verified without tests.
- Allow only validated audio formats that the local decoder can actually handle; fail gracefully when the decoder is unavailable.

## 5. Primary user journey

1. The user opens the local app and sees a compact privacy explanation and current model readiness.
2. They explicitly choose **Record** or **Import audio** and confirm permission to use the recording.
3. EchoArchive ingests the audio into local, private storage and starts transcription on request.
4. They review the segment-by-segment transcript, correct errors, and save revisions.
5. They ask Qwen to **Find meaningful moments**. The model proposes memory cards, each with validated segment references.
6. The user clicks a source snippet to listen to the real recorded moment.
7. They save, search, and export their archive; deletion is always available after confirmation.

See [APP_FLOW.md](APP_FLOW.md) for states, navigation, and exceptional paths.

## 6. Trust, accuracy and ethical boundaries

- **Consent:** Require the uploader to confirm they have permission to record and use the speaker's audio. Do not silently activate the microphone.
- **Provenance:** Preserve raw audio and the unedited initial transcription alongside an editable transcript revision. Clearly label machine-generated summaries as AI interpretations.
- **Hallucinations:** Do not synthesize missing names, dates, quotations, or family relationships. If uncertain, omit or mark for manual review.
- **No impersonation:** No voice cloning, simulated messages from the dead, or invented personal memories.
- **Privacy:** Local-first does **not** imply encryption or protection from other users of the same operating-system account. Document that limitation.
- **Sensitive content:** Avoid including real personal audio in public demo assets or repository commits. Use fictional recordings.

## 7. Success demonstration and metrics

For the contest demo, show a real synthetic recording from a fictional person remembering a fictional local festival or childhood event. Judge-visible proof should include:

- A playable original audio file.
- A real transcribed segment list.
- At least two memory cards created by local Qwen inference.
- Clicking one card to reveal its supporting transcript and seek the audio.
- One transcript correction causing a clear stale-card warning.
- A successful export and, if time permits, safe deletion.

**Do not invent usage statistics.** Track only reproducible results such as actual seconds of inference on test hardware, measured at demonstration time.

## 8. Non-goals for Week 4

- Accounts, cloud sync, collaboration, public family galleries, mobile app installation.
- Guaranteed speaker diarization or word-level alignment.
- Facial recognition, voice cloning, synthetic resurrection, AI séance conversations.
- Unattended transcription of arbitrary private folders.
- Unlimited-length archives or simultaneous GPU-intensive requests.
- End-to-end encryption (unless designed, implemented, and independently tested later).

## 9. Release criteria

Release only if the core two-model pipeline works with real local inference; cards have validated sources; upload, export, deletion and errors are tested; the UI has no dead controls; local privacy claims are accurate; and a genuine demo can be recorded. Log any unsupported platform or model combination.

## 10. Related documents

- [TRD.md](TRD.md): technical decisions and interfaces.
- [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md): data model and API contracts.
- [APP_FLOW.md](APP_FLOW.md): experience map and states.
- [UIUX_BRIEF.md](UIUX_BRIEF.md): product design system.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): phased delivery and quality gates.
