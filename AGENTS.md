# EchoArchive — Agent Guidelines & Architecture Rules

EchoArchive is a local-first application designed to preserve real spoken stories and make them accessible through **Traceable Memories**. The original recording and human-reviewed transcript are the sole authorities; local AI serves only as an indexing and summarization assistant.

## Core Architectural Boundaries

1. **Local-Only Execution:**
   - All transcription and LLM inference must occur on localhost.
   - Speech recognition: local `whisper.cpp` (`whisper-cli`).
   - Memory extraction: local `qwen2.5:1.5b` via Ollama at `http://127.0.0.1:11434`.
   - Backend binds strictly to loopback (`127.0.0.1:8766`).
   - Zero telemetry, zero analytics, zero external network calls during operation.

2. **Source Grounding (Traceable Memories):**
   - Every AI-generated memory card **must** cite at least one valid, existing `transcript_segments` record from the same story.
   - Cards citing non-existent segments, cross-story segments, or containing unverified quotations must be rejected by the evidence validator.
   - The UI and API must present real transcript segment text as the authoritative evidence, never LLM hallucinations.

3. **Security and Subprocess Safety:**
   - **Never use `shell=True`** in `subprocess` calls. Always pass argument arrays.
   - Never interpolate untrusted user input or uploaded filenames into shell command strings.
   - Store ingested audio using generated UUID filenames beneath private directories (`data/media/{uuid}.{ext}`).
   - Prevent path traversal (`../`) and reject symlink escapes.
   - Sanitize all error messages: do not leak raw server filesystem paths or stack traces.

4. **Privacy and Git Hygiene:**
   - Never commit SQLite database files (`*.sqlite3`, `*.sqlite3-wal`).
   - Never commit real or synthetic user audio recordings, raw transcripts, or exported ZIP archives.
   - Never commit model weights (`*.bin`, `*.gguf`).
   - Use only synthetic, fictional test audio fixtures in automated tests and demonstrations.

5. **Ethical Boundaries:**
   - No voice cloning, synthetic resurrection, or AI séance personas.
   - Require explicit affirmative permission confirmation before processing audio.
   - No audio recording without explicit user action in the browser.
