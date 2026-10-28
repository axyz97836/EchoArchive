# EchoArchive — Demonstration Guide & Voiceover Script

This document provides a professional, step-by-step recording plan and timed voiceover narration for demonstrating EchoArchive. All demonstrations use **purely synthetic, fictional test audio** to protect personal privacy.

---

## 1. Technical Setup & Pre-Flight Checklist

1. **Local AI Engine Readiness:**
   - Verify Ollama is running: `curl -s http://127.0.0.1:11434/api/tags`
   - Verify speech model exists: `models/ggml-tiny.en.bin` (74.1 MiB)
   - Verify local Qwen model: `qwen2.5:1.5b` (Q4_K_M GGUF)
   - Verify FFmpeg and whisper-cli in PATH
2. **Start EchoArchive:**
   ```bash
   ./run.sh
   # Server runs on http://127.0.0.1:8766
   ```
3. **Display Settings for Screen Capture:**
   - Viewport: 1280 × 800 or 1440 × 900
   - Clean browser window with no external toolbars or bookmarks
   - Zoom level: 100%
4. **Fictional Test Audio Fixture:**
   - Synthetic speech file: `Vermont Maple Sugar Story` (fictional memory of Aunt Clara's sugar cabin in early spring, duration: ~18 seconds).

---

## 2. Timed Demonstration Plan & Voiceover Script

### Scene 1: Introduction & The Archive After Dark (0:00 – 0:25)
- **On-Screen Action:**
  Browser opens to `http://127.0.0.1:8766`.
  Cursor hovers over the system status pill (`Local AI Ready`).
  Clicks the "Local AI Ready" indicator to show local whisper.cpp and Ollama service statuses.
- **Voiceover Narration:**
  > "Spoken stories fade with time. But the voices of the people who lived them don't have to.
  >
  > Welcome to EchoArchive—a local-first application built for Hacktoberfest 2026's 'Ghost in the Machine' challenge.
  >
  > Unlike cloud platforms that ingest personal recordings into remote servers, EchoArchive operates completely offline on localhost. Every transcription and language model runs on your machine with zero telemetry, zero analytics, and zero external network calls."

### Scene 2: Affirmative Consent & Audio Ingestion (0:25 – 0:55)
- **On-Screen Action:**
  Clicks **Preserve a Story** button.
  Navigates to the Studio screen.
  Shows the microphone level meter and file upload drop zone.
  Enters Title: *"Aunt Clara's Maple Sugar Cabin"* and Speaker: *"Clara's Niece"*.
  Points cursor at the consent checkbox: *"I confirm I have permission to record or use this person's audio."*
  Checks the box and uploads the synthetic WAV file.
  Clicks **Save This Recording**.
- **Voiceover Narration:**
  > "EchoArchive begins with explicit affirmative consent. We believe oral history preservation must respect the speaker's agency—no microphone is ever activated without a deliberate click, and no audio is ingested without explicit permission confirmation.
  >
  > Audio is stored locally in private storage under generated UUIDs, protected against path traversal. Let's save this recording."

### Scene 3: Offline whisper.cpp Transcription (0:55 – 1:20)
- **On-Screen Action:**
  Story Workspace opens.
  The audio player is loaded with seek bar and speed controls.
  Clicks **Transcribe Locally with whisper.cpp**.
  The live background job banner transitions through real stages: `queued` → `preparing` → `transcribing` → `saving` → `succeeded`.
  Chronological transcript segments render with monospace timestamps.
- **Voiceover Narration:**
  > "Transcription runs locally using whisper.cpp with Metal GPU acceleration on Apple Silicon. Notice the honest stage transitions—we never fabricate time percentages.
  >
  > Within seconds, our spoken audio is parsed into timestamped segments. But machine transcripts are not infallible—which brings us to the core ethical foundation of EchoArchive: the human is the sole authority."

### Scene 4: Human Review & Revision Invalidation (1:20 – 1:55)
- **On-Screen Action:**
  Points out the badge: `Awaiting Human Review`.
  Notice the button: `Find Meaningful Moments` is disabled because the transcript has not been reviewed.
  Clicks the inline **Edit** button on Segment 1.
  Corrects *"When I was nine years old in Vermont"* to *"When I was nine years old in rural Vermont"*.
  Clicks **Save**.
  Transcript revision increments from `Revision 1` to `Revision 2`.
  Clicks **Confirm Transcript Reviewed**.
  Badge shifts to sage green: `Reviewed by Human`.
  `Find Meaningful Moments` button becomes active.
- **Voiceover Narration:**
  > "Notice that new machine transcripts start unreviewed. Memory extraction is strictly gated: the system rejects extraction until a human reviews the text.
  >
  > When I correct a segment, EchoArchive increments the transcript revision and automatically invalidates prior review status. A human must explicitly confirm the latest revision. Only once confirmed does the extraction boundary allow us to proceed."

### Scene 5: Local Qwen Memory Extraction & Traceable Memories (1:55 – 2:40)
- **On-Screen Action:**
  Clicks **Find Meaningful Moments**.
  Stepper shows: `Queued` → `Analyzing Transcript` → `Validating Evidence` → `Saving Cards`.
  The Traceable Memory Cards view appears.
  Inspects the card: *"Teaching Maple Tapping"*.
  Points out:
  1. AI Summary labeled as **Current Interpretation**
  2. Theme tags: `Aunt Clara`, `Maple Tapping`, `Patience`
  3. Model provenance: `qwen2.5:1.5b (local inference)`
  4. The **Authoritative Spoken Evidence** box citing exact segment timestamps.
  Clicks the **"Listen to Spoken Passage"** button on the citation.
  The audio player scrubs to that exact second, highlighting the passage with an amber glow as real audio plays.
- **Voiceover Narration:**
  > "EchoArchive invokes local Qwen2.5:1.5b via Ollama using structured JSON schemas.
  >
  > This is our central innovation: Traceable Memories. Every AI-generated card is an interpretive summary, not an authoritative quotation. Crucially, every card is strictly grounded in what was actually spoken.
  >
  > When I click 'Listen to Spoken Passage', EchoArchive streams HTTP byte ranges directly from the original recording, seeking to the exact spoken second. You hear the actual person's voice—not an AI approximation."

### Scene 6: Local Full-Text Search (2:40 – 3:05)
- **On-Screen Action:**
  Returns to Archive home.
  Types `"maple"` in the search bar.
  Live categorized search results appear instantly:
  - Story match
  - Transcript segment match with excerpt snippet
  - Memory card match
  Clicks a transcript search result—instantly opens the story and cues playback.
- **Voiceover Narration:**
  > "Discovery is entirely local. Our parameterized search engine queries story metadata, transcript segments, and memory cards without cloud indexing or external telemetry.
  >
  > Clicking any search result navigates directly into the story workspace, ready for immediate listening."

### Scene 7: Portable Self-Contained ZIP Export (3:05 – 3:35)
- **On-Screen Action:**
  Clicks **Export Story (.zip)**.
  Browser downloads `echoarchive-252da5f5-b179-41d1-ab10-f94d015b747f.zip`.
  Opens the ZIP archive in the filesystem viewer:
  Shows `audio.wav`, `story.json`, `transcript.json`, `memories.json`, `manifest.json`, and `story.html`.
  Double-clicks `story.html`.
  The offline HTML reader opens in browser—plays audio via relative path `<audio src="./audio.wav">` without internet access.
- **Voiceover Narration:**
  > "Your memories belong to you, not a proprietary platform.
  >
  > The export generator creates a self-contained ZIP containing the unmodified original recording bytes, structured JSON transcripts, SHA-256 checksums, and a standalone offline HTML reader.
  >
  > The offline reader has zero remote CDNs, fonts, or scripts. Thirty years from now, you can open this file on an air-gapped machine and listen to the original voice."

### Scene 8: Crash-Safe Deletion & Conclusion (3:35 – 4:00)
- **On-Screen Action:**
  Clicks **Delete Story**.
  Accessible confirmation modal opens with backdrop blur and focus trap.
  Shows the explicit checkbox: *"I understand this permanently removes all local audio and records."*
  Checks the box and clicks **Delete Forever**.
  Story is removed from the archive; toast confirms deletion.
- **Voiceover Narration:**
  > "Data sovereignty also means the right to be forgotten.
  >
  > Deletion uses a durable SQLite cleanup journal to guarantee that database records and private media files are purged safely, even across power interruptions.
  >
  > In an age of synthetic deepfakes and AI hallucinations, EchoArchive stands for truth: preserving real voices, real stories, and verifiable memories.
  >
  > Thank you for exploring EchoArchive."

---

## 3. Video File Verification Standard

When recording and rendering the MP4 demonstration:
- **Format:** MP4 (H.264 video, AAC audio, 1080p 30fps)
- **Audio Balance:** Voiceover clear and audible, browser playback sound audible during audio seeking step
- **Artifact Verification:** Video file saved in private scratch directory; never uploaded to public video hosting without explicit user authorization.
