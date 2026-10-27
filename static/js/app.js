/**
 * EchoArchive — Phase D Frontend Application
 * Strictly local-first speech preservation and traceable memory architecture.
 */

(() => {
  "use strict";

  // Application State
  const state = {
    currentScreen: "screenHome",
    stories: [],
    currentStoryId: null,
    currentStory: null,
    segments: [],
    memoryCards: [],
    activeJobId: null,
    jobPollTimer: null,
    playbackStopTimeout: null,
    mediaRecorder: null,
    recordedChunks: [],
    recordedBlob: null,
    audioContext: null,
    analyserNode: null,
    micStream: null,
    meterAnimationId: null,
    recordStartTime: null,
    recordTimerInterval: null,
    recordDurationSeconds: 0,
    maxRecordDuration: 300, // 5 minutes limit
    selectedUploadFile: null,
  };

  // DOM Elements Cache
  const el = {
    // Nav & System Status
    navHomeBtn: document.getElementById("navHomeBtn"),
    navRecordBtn: document.getElementById("navRecordBtn"),
    navArchiveBtn: document.getElementById("navArchiveBtn"),
    navPrivacyBtn: document.getElementById("navPrivacyBtn"),
    brandHomeLink: document.getElementById("brandHomeLink"),
    statusDot: document.getElementById("statusDot"),
    statusLabel: document.getElementById("statusLabel"),
    systemStatusBadge: document.getElementById("systemStatusBadge"),
    srAnnouncer: document.getElementById("srAnnouncer"),
    toastContainer: document.getElementById("toastContainer"),

    // Screen 1: Home
    screenHome: document.getElementById("screenHome"),
    heroStartRecordBtn: document.getElementById("heroStartRecordBtn"),
    heroUploadBtn: document.getElementById("heroUploadBtn"),
    heroBrowseArchiveBtn: document.getElementById("heroBrowseArchiveBtn"),

    // Screen 2: Record / Upload
    screenRecordUpload: document.getElementById("screenRecordUpload"),
    tabRecordBtn: document.getElementById("tabRecordBtn"),
    tabUploadBtn: document.getElementById("tabUploadBtn"),
    panelRecord: document.getElementById("panelRecord"),
    panelUpload: document.getElementById("panelUpload"),
    startRecordBtn: document.getElementById("startRecordBtn"),
    stopRecordBtn: document.getElementById("stopRecordBtn"),
    replayRecordBtn: document.getElementById("replayRecordBtn"),
    discardRecordBtn: document.getElementById("discardRecordBtn"),
    recordTimer: document.getElementById("recordTimer"),
    recordPulse: document.getElementById("recordPulse"),
    recordStatusLabel: document.getElementById("recordStatusLabel"),
    micMeterCanvas: document.getElementById("micMeterCanvas"),
    micErrorNotice: document.getElementById("micErrorNotice"),
    recordedAudioPreview: document.getElementById("recordedAudioPreview"),
    fileDropZone: document.getElementById("fileDropZone"),
    audioFileInput: document.getElementById("audioFileInput"),
    selectedFileInfo: document.getElementById("selectedFileInfo"),
    storyIngestForm: document.getElementById("storyIngestForm"),
    storyTitleInput: document.getElementById("storyTitleInput"),
    storySpeakerInput: document.getElementById("storySpeakerInput"),
    consentCheckbox: document.getElementById("consentCheckbox"),
    submitStoryBtn: document.getElementById("submitStoryBtn"),

    // Screen 3: Transcript Review
    screenTranscript: document.getElementById("screenTranscript"),
    mainAudioElement: document.getElementById("mainAudioElement"),
    masterPlayPauseBtn: document.getElementById("masterPlayPauseBtn"),
    masterPlayText: document.getElementById("masterPlayText"),
    masterPlayIcon: document.getElementById("masterPlayIcon"),
    playerStoryTitle: document.getElementById("playerStoryTitle"),
    playerTimeDisplay: document.getElementById("playerTimeDisplay"),
    playerScrubBar: document.getElementById("playerScrubBar"),
    playerSpeedBtn: document.getElementById("playerSpeedBtn"),
    transcriptRevBadge: document.getElementById("transcriptRevBadge"),
    reviewStateBadge: document.getElementById("reviewStateBadge"),
    confirmReviewBtn: document.getElementById("confirmReviewBtn"),
    proceedToExtractBtn: document.getElementById("proceedToExtractBtn"),
    transcriptExportBtn: document.getElementById("transcriptExportBtn"),
    transcriptDeleteBtn: document.getElementById("transcriptDeleteBtn"),
    transcribeJobBanner: document.getElementById("transcribeJobBanner"),
    transcribeJobMsg: document.getElementById("transcribeJobMsg"),
    transcriptSegmentsList: document.getElementById("transcriptSegmentsList"),

    // Screen 4: Extraction Stepper
    screenExtracting: document.getElementById("screenExtracting"),
    stepQueued: document.getElementById("stepQueued"),
    stepAnalyzing: document.getElementById("stepAnalyzing"),
    stepValidating: document.getElementById("stepValidating"),
    stepSaving: document.getElementById("stepSaving"),
    extractionErrorBox: document.getElementById("extractionErrorBox"),
    extractErrCode: document.getElementById("extractErrCode"),
    extractErrMsg: document.getElementById("extractErrMsg"),
    cancelExtractionBtn: document.getElementById("cancelExtractionBtn"),
    retryExtractionBtn: document.getElementById("retryExtractionBtn"),

    // Screen 5: Archive
    screenArchive: document.getElementById("screenArchive"),
    storiesCountLabel: document.getElementById("storiesCountLabel"),
    archiveSearchInput: document.getElementById("archiveSearchInput"),
    searchResultsSection: document.getElementById("searchResultsSection"),
    searchResultsHeading: document.getElementById("searchResultsHeading"),
    searchResultsSub: document.getElementById("searchResultsSub"),
    searchResultsList: document.getElementById("searchResultsList"),
    clearSearchBtn: document.getElementById("clearSearchBtn"),
    archiveEmptyState: document.getElementById("archiveEmptyState"),
    emptyRecordBtn: document.getElementById("emptyRecordBtn"),
    storiesGrid: document.getElementById("storiesGrid"),

    // Screen 6: Memories Detail
    screenMemories: document.getElementById("screenMemories"),
    backToTranscriptBtn: document.getElementById("backToTranscriptBtn"),
    memoriesStoryMeta: document.getElementById("memoriesStoryMeta"),
    regenerateMemoriesBtn: document.getElementById("regenerateMemoriesBtn"),
    memoriesExportBtn: document.getElementById("memoriesExportBtn"),
    memoriesDeleteBtn: document.getElementById("memoriesDeleteBtn"),
    staleCardsBanner: document.getElementById("staleCardsBanner"),
    bannerRegenerateBtn: document.getElementById("bannerRegenerateBtn"),
    memoryCardsList: document.getElementById("memoryCardsList"),

    // Modals
    deleteConfirmModal: document.getElementById("deleteConfirmModal"),
    deleteStoryTitleLabel: document.getElementById("deleteStoryTitleLabel"),
    deleteConfirmCheckbox: document.getElementById("deleteConfirmCheckbox"),
    cancelDeleteBtn: document.getElementById("cancelDeleteBtn"),
    confirmDeleteBtn: document.getElementById("confirmDeleteBtn"),
    privacyModal: document.getElementById("privacyModal"),
    closePrivacyBtn: document.getElementById("closePrivacyBtn"),
  };

  // Helper Utilities
  function announce(msg) {
    if (el.srAnnouncer) {
      el.srAnnouncer.textContent = msg;
    }
  }

  function showToast(message, type = "info") {
    if (!el.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type === "error" ? "toast-error" : type === "success" ? "toast-success" : ""}`;
    toast.textContent = message;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      setTimeout(() => toast.remove(), 250);
    }, 4000);
  }

  function formatTimeSeconds(totalSec) {
    if (isNaN(totalSec) || totalSec < 0) return "00:00";
    const minutes = Math.floor(totalSec / 60);
    const seconds = Math.floor(totalSec % 60);
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function formatTimestampMs(ms) {
    if (isNaN(ms) || ms < 0) return "00:00.000";
    const totalSeconds = ms / 1000;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = (totalSeconds % 60).toFixed(3);
    const padSec = parseFloat(seconds) < 10 ? `0${seconds}` : seconds;
    return `${String(minutes).padStart(2, "0")}:${padSec}`;
  }

  // Navigation Controller
  function navigateTo(screenId, pushState = true) {
    // Stop any audio playback boundary timeouts
    if (state.playbackStopTimeout) {
      clearTimeout(state.playbackStopTimeout);
      state.playbackStopTimeout = null;
    }

    const screens = [
      el.screenHome,
      el.screenRecordUpload,
      el.screenTranscript,
      el.screenExtracting,
      el.screenArchive,
      el.screenMemories,
    ];

    screens.forEach((s) => {
      if (s) s.classList.remove("active");
    });

    const target = document.getElementById(screenId);
    if (target) {
      target.classList.add("active");
      state.currentScreen = screenId;
      window.scrollTo(0, 0);
    }

    // Update active state in nav buttons
    [el.navHomeBtn, el.navRecordBtn, el.navArchiveBtn].forEach((btn) => {
      if (btn) {
        btn.classList.toggle("active", btn.dataset.target === screenId);
      }
    });

    // Hash update
    if (pushState) {
      let hash = "#home";
      if (screenId === "screenRecordUpload") hash = "#record";
      else if (screenId === "screenArchive") hash = "#archive";
      else if (screenId === "screenTranscript" && state.currentStoryId) hash = `#story/${state.currentStoryId}`;
      else if (screenId === "screenMemories" && state.currentStoryId) hash = `#story/${state.currentStoryId}/memories`;
      else if (screenId === "screenExtracting" && state.currentStoryId) hash = `#story/${state.currentStoryId}/extract`;

      if (window.location.hash !== hash) {
        window.history.pushState(null, "", hash);
      }
    }

    announce(`Navigated to ${screenId.replace("screen", "")}`);
  }

  // System Health Polling
  async function checkSystemHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check degraded");
      const data = await res.json();
      const services = data.services || {};
      const speechReady = services.speech_recognition?.ready;
      const llmReady = services.language_model?.ready;

      if (data.status === "ready" && speechReady && llmReady) {
        el.statusDot.className = "status-dot ready";
        el.statusLabel.textContent = "Local AI Ready";
        el.systemStatusBadge.title = "Whisper.cpp and Qwen2.5 are verified and ready on localhost.";
      } else {
        el.statusDot.className = "status-dot degraded";
        el.statusLabel.textContent = "Local Degraded";
        const missing = [];
        if (!speechReady) missing.push("Whisper");
        if (!llmReady) missing.push("Qwen");
        el.systemStatusBadge.title = `Local dependencies degraded: ${missing.join(", ")}`;
      }
    } catch {
      el.statusDot.className = "status-dot error";
      el.statusLabel.textContent = "Offline";
      el.systemStatusBadge.title = "Cannot reach EchoArchive local loopback server.";
    }
  }

  // Screen 2: Real Microphone Recording Logic
  function getSupportedMimeType() {
    const types = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
      "audio/wav",
    ];
    for (const t of types) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return "";
  }

  function drawAudioLevelMeter() {
    if (!state.analyserNode || !el.micMeterCanvas) return;
    const canvas = el.micMeterCanvas;
    const ctx = canvas.getContext("2d");
    const bufferLength = state.analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      if (!state.mediaRecorder || state.mediaRecorder.state !== "recording") {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }

      state.meterAnimationId = requestAnimationFrame(draw);
      state.analyserNode.getByteFrequencyData(dataArray);

      ctx.fillStyle = "#1B252B";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const average = sum / bufferLength;
      const normalized = Math.min(1.0, average / 110.0);

      // Draw responsive visual signal bars
      const barCount = 36;
      const barWidth = canvas.width / barCount - 2;
      for (let i = 0; i < barCount; i++) {
        const binIndex = Math.floor((i / barCount) * (bufferLength / 2));
        const val = dataArray[binIndex] / 255.0;
        const barHeight = Math.max(4, val * (canvas.height - 8));
        const x = i * (barWidth + 2);
        const y = (canvas.height - barHeight) / 2;

        ctx.fillStyle = normalized > 0.85 ? "#8C4B4A" : "#E5B65F";
        ctx.fillRect(x, y, barWidth, barHeight);
      }
    };

    draw();
  }

  async function startMicrophoneRecording() {
    el.micErrorNotice.style.display = "none";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showMicError("Microphone access is not supported by this browser.");
      return;
    }

    const mimeType = getSupportedMimeType();
    if (!mimeType) {
      showMicError("No supported browser audio recording format was detected.");
      return;
    }

    try {
      state.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Web Audio API setup for real audio signal level meter
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      state.audioContext = new AudioCtx();
      const source = state.audioContext.createMediaStreamSource(state.micStream);
      state.analyserNode = state.audioContext.createAnalyser();
      state.analyserNode.fftSize = 256;
      source.connect(state.analyserNode);

      state.recordedChunks = [];
      state.mediaRecorder = new MediaRecorder(state.micStream, { mimeType });

      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          state.recordedChunks.push(event.data);
        }
      };

      state.mediaRecorder.onstop = () => {
        state.recordedBlob = new Blob(state.recordedChunks, { type: mimeType });
        if (el.recordedAudioPreview) {
          el.recordedAudioPreview.src = URL.createObjectURL(state.recordedBlob);
        }
        el.replayRecordBtn.disabled = false;
        el.discardRecordBtn.disabled = false;
        validateIngestFormState();
      };

      state.mediaRecorder.start(250); // Slice every 250ms
      state.recordStartTime = Date.now();
      state.recordDurationSeconds = 0;
      el.recordTimer.textContent = "00:00";
      el.recordPulse.classList.add("active");
      el.recordStatusLabel.textContent = "Recording in progress...";
      el.startRecordBtn.disabled = true;
      el.stopRecordBtn.disabled = false;
      el.replayRecordBtn.disabled = true;
      el.discardRecordBtn.disabled = true;

      drawAudioLevelMeter();

      // Timer Interval enforcing 5-minute maximum limit
      state.recordTimerInterval = setInterval(() => {
        state.recordDurationSeconds = Math.floor((Date.now() - state.recordStartTime) / 1000);
        el.recordTimer.textContent = formatTimeSeconds(state.recordDurationSeconds);

        if (state.recordDurationSeconds >= state.maxRecordDuration) {
          stopMicrophoneRecording();
          showToast("Maximum recording duration (5 minutes) reached.", "info");
        }
      }, 1000);

      announce("Microphone recording started.");
    } catch (err) {
      showMicError(
        err.name === "NotAllowedError"
          ? "Microphone permission was denied. Please allow microphone access in your browser or use the file upload alternative."
          : `Failed to access microphone: ${err.message || "Unknown error"}`
      );
    }
  }

  function stopMicrophoneRecording() {
    if (state.recordTimerInterval) {
      clearInterval(state.recordTimerInterval);
      state.recordTimerInterval = null;
    }

    if (state.meterAnimationId) {
      cancelAnimationFrame(state.meterAnimationId);
      state.meterAnimationId = null;
    }

    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }

    if (state.micStream) {
      state.micStream.getTracks().forEach((track) => track.stop());
      state.micStream = null;
    }

    if (state.audioContext && state.audioContext.state !== "closed") {
      state.audioContext.close();
      state.audioContext = null;
    }

    el.recordPulse.classList.remove("active");
    el.recordStatusLabel.textContent = "Recording complete. Ready to preserve.";
    el.startRecordBtn.disabled = false;
    el.stopRecordBtn.disabled = true;
    announce("Microphone recording stopped.");
  }

  function discardMicrophoneRecording() {
    stopMicrophoneRecording();
    state.recordedChunks = [];
    state.recordedBlob = null;
    state.recordDurationSeconds = 0;
    el.recordTimer.textContent = "00:00";
    el.recordStatusLabel.textContent = "Microphone ready to initialize";
    el.replayRecordBtn.disabled = true;
    el.discardRecordBtn.disabled = true;
    if (el.recordedAudioPreview) {
      el.recordedAudioPreview.src = "";
    }
    const canvas = el.micMeterCanvas;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    validateIngestFormState();
    announce("Recording discarded.");
  }

  function showMicError(msg) {
    el.micErrorNotice.textContent = msg;
    el.micErrorNotice.style.display = "block";
    announce(`Microphone error: ${msg}`);
  }

  // Screen 2: Ingest Form & Validation
  function validateIngestFormState() {
    const hasAudio = state.recordedBlob !== null || state.selectedUploadFile !== null;
    const hasTitle = (el.storyTitleInput.value || "").trim().length > 0;
    const hasConsent = el.consentCheckbox.checked;
    el.submitStoryBtn.disabled = !(hasAudio && hasTitle && hasConsent);
  }

  async function handleStoryIngestSubmit(e) {
    e.preventDefault();
    if (el.submitStoryBtn.disabled) return;

    const title = el.storyTitleInput.value.trim();
    const speaker = el.storySpeakerInput.value.trim();
    const consent = el.consentCheckbox.checked;

    if (!title) {
      showToast("Story title is required.", "error");
      return;
    }

    const formData = new FormData();
    formData.append("title", title);
    if (speaker) formData.append("speaker_label", speaker);
    formData.append("permission_confirmed", consent ? "true" : "false");

    if (state.recordedBlob) {
      const ext = state.recordedBlob.type.includes("mp4") ? "mp4" : "webm";
      formData.append("audio", state.recordedBlob, `recording.${ext}`);
    } else if (state.selectedUploadFile) {
      formData.append("audio", state.selectedUploadFile, state.selectedUploadFile.name);
    } else {
      showToast("Please record or select an audio story.", "error");
      return;
    }

    el.submitStoryBtn.disabled = true;
    el.submitStoryBtn.textContent = "Preserving Story...";

    try {
      const res = await fetch("/api/stories", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error?.message || "Story ingestion failed.");
      }

      const story = await res.json();
      showToast("Story preserved locally. Starting speech transcription...", "success");

      // Reset recording form
      discardMicrophoneRecording();
      state.selectedUploadFile = null;
      el.selectedFileInfo.style.display = "none";
      el.storyTitleInput.value = "";
      el.storySpeakerInput.value = "";
      el.consentCheckbox.checked = false;

      // Start offline whisper transcription
      const transRes = await fetch(`/api/stories/${story.id}/transcribe`, {
        method: "POST",
      });

      if (!transRes.ok) {
        const errData = await transRes.json().catch(() => ({}));
        showToast(`Transcription enqueue error: ${errData.error?.message || "Unknown error"}`, "error");
      }

      // Navigate directly to transcript review screen
      loadStoryWorkspace(story.id);
    } catch (err) {
      showToast(err.message, "error");
      el.submitStoryBtn.disabled = false;
      el.submitStoryBtn.textContent = "Preserve and Transcribe Story";
    }
  }

  // Screen 3: Load Story Workspace (Transcript & Segments)
  async function loadStoryWorkspace(storyId) {
    state.currentStoryId = storyId;
    navigateTo("screenTranscript");

    try {
      const [storyRes, segsRes] = await Promise.all([
        fetch(`/api/stories/${storyId}`),
        fetch(`/api/stories/${storyId}/segments`),
      ]);

      if (!storyRes.ok) throw new Error("Could not load story details.");
      state.currentStory = await storyRes.json();
      state.segments = segsRes.ok ? (await segsRes.json()).segments || [] : [];

      renderTranscriptWorkspace();

      // Check if transcription job is running or needs polling
      if (state.currentStory.current_job && ["queued", "running"].includes(state.currentStory.current_job.status)) {
        pollJobStatus(state.currentStory.current_job.id, "transcribe");
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function renderTranscriptWorkspace() {
    const story = state.currentStory;
    if (!story) return;

    el.playerStoryTitle.textContent = story.title;
    el.mainAudioElement.src = `/api/stories/${story.id}/audio`;
    el.mainAudioElement.load();

    el.transcriptRevBadge.textContent = `Revision ${story.transcript_revision}`;
    if (story.is_reviewed) {
      el.reviewStateBadge.className = "badge badge-sage";
      el.reviewStateBadge.textContent = "Reviewed by Human";
      el.confirmReviewBtn.disabled = true;
      el.confirmReviewBtn.textContent = "Transcript Verified";
    } else {
      el.reviewStateBadge.className = "badge badge-neutral";
      el.reviewStateBadge.textContent = "Awaiting Human Review";
      el.confirmReviewBtn.disabled = false;
      el.confirmReviewBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        Confirm Transcript Reviewed
      `;
    }

    // Enable memory extraction if segments exist
    el.proceedToExtractBtn.disabled = state.segments.length === 0;

    if (el.transcriptExportBtn) {
      el.transcriptExportBtn.onclick = () => exportStoryZip(story.id);
    }
    if (el.transcriptDeleteBtn) {
      el.transcriptDeleteBtn.onclick = () => openDeleteModal(story.id, story.title, el.transcriptDeleteBtn);
    }

    renderSegmentsList();
  }

  function renderSegmentsList() {
    el.transcriptSegmentsList.innerHTML = "";
    if (state.segments.length === 0) {
      el.transcriptSegmentsList.innerHTML = `
        <div class="empty-state" style="padding: var(--space-xl);">
          <p style="color: var(--color-parchment-muted); margin: 0;">No transcript segments generated yet. Speech recognition is processing.</p>
        </div>
      `;
      return;
    }

    state.segments.forEach((seg) => {
      const card = document.createElement("div");
      card.className = "segment-card";
      card.id = `seg-${seg.id}`;

      const startSec = (seg.start_ms / 1000).toFixed(2);
      const endSec = (seg.end_ms / 1000).toFixed(2);
      const isEdited = seg.user_edited === 1;

      card.innerHTML = `
        <div class="segment-header">
          <div class="segment-meta">
            <span>[${formatTimestampMs(seg.start_ms)} &rarr; ${formatTimestampMs(seg.end_ms)}]</span>
            <span class="badge ${isEdited ? "badge-amber" : "badge-neutral"}">${isEdited ? "Human Corrected" : "Machine"}</span>
          </div>
          <div class="segment-actions">
            <button type="button" class="btn btn-secondary btn-sm play-seg-btn" data-start="${seg.start_ms / 1000}" data-end="${seg.end_ms / 1000}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="6 3 20 12 6 21 6 3"/></svg>
              Play
            </button>
            <button type="button" class="btn btn-outline-amber btn-sm edit-seg-btn">
              Edit
            </button>
          </div>
        </div>
        <p class="segment-text">${escapeHtml(seg.text)}</p>
        <textarea class="segment-editor">${escapeHtml(seg.text)}</textarea>
        <div class="editor-actions" style="display: none; justify-content: flex-end; gap: 8px; margin-top: 6px;">
          <button type="button" class="btn btn-secondary btn-sm cancel-seg-btn">Cancel</button>
          <button type="button" class="btn btn-primary btn-sm save-seg-btn">Save Correction</button>
        </div>
      `;

      // Segment Audio Playback Listener
      const playBtn = card.querySelector(".play-seg-btn");
      playBtn.addEventListener("click", () => {
        playAudioSegment(seg.start_ms / 1000, seg.end_ms / 1000, card);
      });

      // Segment Edit Toggles
      const editBtn = card.querySelector(".edit-seg-btn");
      const cancelBtn = card.querySelector(".cancel-seg-btn");
      const saveBtn = card.querySelector(".save-seg-btn");
      const textP = card.querySelector(".segment-text");
      const editor = card.querySelector(".segment-editor");
      const editorActions = card.querySelector(".editor-actions");

      editBtn.addEventListener("click", () => {
        textP.style.display = "none";
        editor.style.display = "block";
        editorActions.style.display = "flex";
        editBtn.style.display = "none";
        editor.focus();
      });

      cancelBtn.addEventListener("click", () => {
        editor.value = seg.text;
        textP.style.display = "block";
        editor.style.display = "none";
        editorActions.style.display = "none";
        editBtn.style.display = "inline-flex";
      });

      saveBtn.addEventListener("click", async () => {
        const newText = editor.value.trim();
        if (!newText) {
          showToast("Segment text cannot be empty.", "error");
          return;
        }

        try {
          const res = await fetch(`/api/stories/${state.currentStoryId}/segments/${seg.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: newText,
              expected_revision: state.currentStory.transcript_revision,
            }),
          });

          if (res.status === 409) {
            showToast("Revision conflict: Transcript was modified. Reloading latest version.", "error");
            loadStoryWorkspace(state.currentStoryId);
            return;
          }

          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error?.message || "Failed to update segment.");
          }

          const data = await res.json();
          seg.text = newText;
          seg.user_edited = 1;
          state.currentStory.transcript_revision = data.transcript_revision;
          state.currentStory.is_reviewed = false;
          showToast("Correction saved. Review confirmation invalidated until re-confirmed.", "success");
          renderTranscriptWorkspace();
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      el.transcriptSegmentsList.appendChild(card);
    });
  }

  // Audio Playback with Exact Seeking and Active Segment Highlighting
  function playAudioSegment(startSec, endSec, highlightEl = null) {
    const audio = el.mainAudioElement;
    if (!audio) return;

    if (state.playbackStopTimeout) {
      clearTimeout(state.playbackStopTimeout);
      state.playbackStopTimeout = null;
    }

    // Clear active highlight from all cards
    document.querySelectorAll(".playing-active, .playing-glow").forEach((elem) => {
      elem.classList.remove("playing-active");
      elem.classList.remove("playing-glow");
    });

    if (highlightEl) {
      if (highlightEl.classList.contains("evidence-quote-box")) {
        highlightEl.classList.add("playing-glow");
      } else {
        highlightEl.classList.add("playing-active");
      }
    }

    const seekAndPlay = () => {
      audio.currentTime = Math.max(0, startSec);
      audio.play().then(() => {
        el.masterPlayText.textContent = "Pause";
        // Calculate bounded duration
        const durationMs = Math.max(200, (endSec - startSec) * 1000);
        state.playbackStopTimeout = setTimeout(() => {
          audio.pause();
          el.masterPlayText.textContent = "Play";
          if (highlightEl) {
            highlightEl.classList.remove("playing-active");
            highlightEl.classList.remove("playing-glow");
          }
        }, durationMs);
      }).catch((err) => {
        showToast("Audio playback interrupted: " + err.message, "error");
      });
    };

    if (audio.readyState >= 1) {
      seekAndPlay();
    } else {
      audio.addEventListener("loadedmetadata", seekAndPlay, { once: true });
      audio.load();
    }
  }

  // Job Polling Controller
  function pollJobStatus(jobId, kind) {
    if (state.jobPollTimer) clearInterval(state.jobPollTimer);

    if (kind === "transcribe") {
      el.transcribeJobBanner.style.display = "flex";
      el.transcribeJobMsg.textContent = "Local whisper.cpp transcribing audio...";
    }

    state.jobPollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        if (kind === "transcribe") {
          el.transcribeJobMsg.textContent = `Transcription stage: ${job.stage}...`;
        } else if (kind === "extract") {
          updateExtractionStepper(job.stage);
        }

        if (job.status === "succeeded") {
          clearInterval(state.jobPollTimer);
          state.jobPollTimer = null;

          if (kind === "transcribe") {
            el.transcribeJobBanner.style.display = "none";
            showToast("Transcription completed successfully.", "success");
            loadStoryWorkspace(state.currentStoryId);
          } else if (kind === "extract") {
            showToast("Memory extraction complete.", "success");
            loadMemoriesScreen(state.currentStoryId);
          }
        } else if (job.status === "failed") {
          clearInterval(state.jobPollTimer);
          state.jobPollTimer = null;

          if (kind === "transcribe") {
            el.transcribeJobBanner.style.display = "none";
            showToast(`Transcription failed: ${job.error_message || job.error_code}`, "error");
          } else if (kind === "extract") {
            showExtractionFailure(job.error_code, job.error_message);
          }
        }
      } catch (err) {
        console.error("Job polling error", err);
      }
    }, 1200);
  }

  // Screen 4: Memory Extraction Stepper
  function updateExtractionStepper(stage) {
    const steps = [el.stepQueued, el.stepAnalyzing, el.stepValidating, el.stepSaving];
    steps.forEach((s) => s.classList.remove("current", "completed"));

    if (stage === "queued") {
      el.stepQueued.classList.add("current");
    } else if (stage === "analyzing" || stage === "extracting") {
      el.stepQueued.classList.add("completed");
      el.stepAnalyzing.classList.add("current");
    } else if (stage === "validating") {
      el.stepQueued.classList.add("completed");
      el.stepAnalyzing.classList.add("completed");
      el.stepValidating.classList.add("current");
    } else if (stage === "saving") {
      steps.slice(0, 3).forEach((s) => s.classList.add("completed"));
      el.stepSaving.classList.add("current");
    }
  }

  function showExtractionFailure(code, msg) {
    el.extractionErrorBox.style.display = "flex";
    el.extractErrCode.textContent = code || "EXTRACTION_FAILED";
    let message = msg || "An error occurred during local memory extraction.";

    if (code === "OLLAMA_UNAVAILABLE") {
      message = "Ollama is not running at 127.0.0.1:11434. Please start Ollama locally.";
    } else if (code === "MODEL_NOT_FOUND") {
      message = "Model qwen2.5:1.5b is missing. Run 'ollama pull qwen2.5:1.5b'.";
    } else if (code === "REVISION_CONFLICT") {
      message = "Transcript revision changed during extraction. Please restart extraction.";
    }

    el.extractErrMsg.textContent = message;
    el.retryExtractionBtn.style.display = "inline-flex";
  }

  async function triggerMemoryExtraction() {
    if (!state.currentStoryId) return;
    navigateTo("screenExtracting");
    el.extractionErrorBox.style.display = "none";
    el.retryExtractionBtn.style.display = "none";
    updateExtractionStepper("queued");

    try {
      const res = await fetch(`/api/stories/${state.currentStoryId}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: state.currentStory?.transcript_revision,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showExtractionFailure(err.error?.code, err.error?.message);
        return;
      }

      const job = await res.json();
      pollJobStatus(job.job_id, "extract");
    } catch (err) {
      showExtractionFailure("NETWORK_ERROR", err.message);
    }
  }

  // Screen 5: Story Archive Library
  async function loadStoryArchive() {
    navigateTo("screenArchive");
    el.storiesCountLabel.textContent = "Loading saved stories...";

    try {
      const res = await fetch("/api/stories?limit=100");
      if (!res.ok) throw new Error("Failed to load stories from archive.");
      const data = await res.json();
      state.stories = data.stories || [];

      renderStoriesGrid(state.stories);
    } catch (err) {
      showToast(err.message, "error");
      el.storiesCountLabel.textContent = "Unable to load stories.";
    }
  }

  function renderStoriesGrid(storiesList) {
    el.storiesGrid.innerHTML = "";
    const count = storiesList.length;

    if (count === 0) {
      el.storiesCountLabel.textContent = "0 stories preserved";
      el.archiveEmptyState.style.display = "block";
      return;
    }

    el.archiveEmptyState.style.display = "none";
    el.storiesCountLabel.textContent = `${count} ${count === 1 ? "story" : "stories"} preserved in local archive`;

    storiesList.forEach((story) => {
      const card = document.createElement("div");
      card.className = "story-archive-card";
      card.tabIndex = 0;
      card.role = "listitem";

      const createdDate = new Date(story.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
      const durationSec = Math.round((story.audio_duration_ms || 0) / 1000);
      const memoryCount = story.memory_cards_count || 0;
      const isReviewed = story.is_reviewed;

      card.innerHTML = `
        <div>
          <h2 class="story-card-title">${escapeHtml(story.title)}</h2>
          <div class="story-meta-line">
            <span>${escapeHtml(story.speaker_label || "Unknown Speaker")}</span>
            <span>&bull;</span>
            <span>${createdDate}</span>
            <span>&bull;</span>
            <span>${formatTimeSeconds(durationSec)}</span>
          </div>
        </div>
        <div class="story-tags-row">
          <span class="badge ${isReviewed ? "badge-sage" : "badge-neutral"}">
            ${isReviewed ? "Verified Transcript" : "Needs Review"}
          </span>
          <span class="badge ${memoryCount > 0 ? "badge-amber" : "badge-neutral"}">
            ${memoryCount} ${memoryCount === 1 ? "Memory" : "Memories"}
          </span>
          <span class="badge badge-neutral">Rev ${story.transcript_revision}</span>
        </div>
      `;

      const actionsRow = document.createElement("div");
      actionsRow.className = "story-card-actions";
      actionsRow.innerHTML = `
        <button type="button" class="btn-action-icon btn-export-zip" title="Export story as portable ZIP archive">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
          Export ZIP
        </button>
        <button type="button" class="btn-action-icon btn-action-delete btn-delete-story" title="Permanently delete story">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
          Delete
        </button>
      `;

      const expBtn = actionsRow.querySelector(".btn-export-zip");
      expBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        exportStoryZip(story.id);
      });

      const delBtn = actionsRow.querySelector(".btn-delete-story");
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openDeleteModal(story.id, story.title, delBtn);
      });

      card.appendChild(actionsRow);

      const openStory = () => {
        if (memoryCount > 0) {
          loadMemoriesScreen(story.id);
        } else {
          loadStoryWorkspace(story.id);
        }
      };

      card.addEventListener("click", openStory);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openStory();
        }
      });

      el.storiesGrid.appendChild(card);
    });
  }

  // Screen 6: Traceable Memory Cards Detail
  async function loadMemoriesScreen(storyId) {
    state.currentStoryId = storyId;
    navigateTo("screenMemories");

    try {
      const [storyRes, cardsRes] = await Promise.all([
        fetch(`/api/stories/${storyId}`),
        fetch(`/api/stories/${storyId}/cards`),
      ]);

      if (!storyRes.ok || !cardsRes.ok) throw new Error("Could not load memories.");
      state.currentStory = await storyRes.json();
      const cardsData = await cardsRes.json();
      state.memoryCards = cardsData.cards || [];

      // Setup audio element for seeking
      el.mainAudioElement.src = `/api/stories/${storyId}/audio`;
      el.mainAudioElement.load();

      renderMemoriesDetail(cardsData);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function renderMemoriesDetail(cardsData) {
    const story = state.currentStory;
    el.memoriesStoryMeta.textContent = `Story: "${story.title}" — ${story.speaker_label || "Unknown Speaker"} (Current Revision: ${cardsData.current_transcript_revision})`;

    // Stale Cards Banner
    if (cardsData.has_stale_cards) {
      el.staleCardsBanner.style.display = "flex";
    } else {
      el.staleCardsBanner.style.display = "none";
    }

    if (el.memoriesExportBtn) {
      el.memoriesExportBtn.onclick = () => exportStoryZip(story.id);
    }
    if (el.memoriesDeleteBtn) {
      el.memoriesDeleteBtn.onclick = () => openDeleteModal(story.id, story.title, el.memoriesDeleteBtn);
    }

    el.memoryCardsList.innerHTML = "";
    if (state.memoryCards.length === 0) {
      el.memoryCardsList.innerHTML = `
        <div class="empty-state">
          <p style="color: var(--color-parchment-muted); margin-bottom: var(--space-md);">No memory cards extracted yet for this story.</p>
          <button type="button" class="btn btn-primary btn-sm" id="emptyExtractMemoriesBtn">Extract Memories with Qwen</button>
        </div>
      `;
      const btn = document.getElementById("emptyExtractMemoriesBtn");
      if (btn) btn.addEventListener("click", triggerMemoryExtraction);
      return;
    }

    state.memoryCards.forEach((card) => {
      const cardEl = document.createElement("article");
      cardEl.className = `memory-card ${card.is_stale ? "stale-card" : ""}`;
      cardEl.id = `card-${card.id}`;

      // Themes tags
      const themesHtml = (card.themes || [])
        .map((t) => `<span class="theme-pill">#${escapeHtml(t)}</span>`)
        .join(" ");

      // Sources Passages
      const sourcesHtml = (card.sources || [])
        .map((src) => {
          return `
            <div class="evidence-quote-box" id="evidence-${src.segment_id}">
              <div class="evidence-quote-text">&ldquo;${escapeHtml(src.text)}&rdquo;</div>
              <div class="evidence-meta-bar">
                <span>[${formatTimestampMs(src.start_ms)} &rarr; ${formatTimestampMs(src.end_ms)}] &bull; Segment #${src.segment_index + 1}</span>
                <button type="button" class="listen-passage-btn" data-start="${src.start_seconds}" data-end="${src.end_seconds}" data-target-id="evidence-${src.segment_id}">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="6 3 20 12 6 21 6 3"/></svg>
                  Listen to Spoken Passage
                </button>
              </div>
            </div>
          `;
        })
        .join("");

      cardEl.innerHTML = `
        <div class="memory-card-header">
          <div class="memory-title-area">
            <h2 class="memory-card-title">${escapeHtml(card.title)}</h2>
            <div class="memory-provenance-info">
              <span class="badge badge-neutral">${escapeHtml(card.model_provenance || "qwen2.5:1.5b (local)")}</span>
              <span class="badge badge-neutral">Rev ${card.generated_from_revision}</span>
              ${card.is_stale ? `<span class="badge badge-burgundy">Stale</span>` : ""}
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <label for="reviewState-${card.id}" style="font-size: 0.8rem; color: var(--color-parchment-muted);">Status:</label>
            <select id="reviewState-${card.id}" class="form-input" style="width: auto; padding: 4px 8px; font-size: 0.82rem;">
              <option value="draft" ${card.review_state === "draft" ? "selected" : ""}>Draft</option>
              <option value="accepted" ${card.review_state === "accepted" ? "selected" : ""}>Accepted</option>
              <option value="dismissed" ${card.review_state === "dismissed" ? "selected" : ""}>Dismissed</option>
            </select>
          </div>
        </div>

        ${card.is_stale ? `
          <div class="stale-warning-banner" style="margin: var(--space-sm) var(--space-lg); border-radius: 4px;">
            <span style="font-size: 0.82rem;">${escapeHtml(card.stale_reason || "Transcript revised since generation.")}</span>
          </div>
        ` : ""}

        <div class="memory-summary-box">
          <div class="memory-summary-label">AI Index Interpretation</div>
          ${escapeHtml(card.summary)}
        </div>

        ${themesHtml ? `<div class="memory-themes-list">${themesHtml}</div>` : ""}

        <div class="evidence-section">
          <div class="evidence-heading">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
            Verified Transcript Evidence
          </div>
          <div class="evidence-passages-list">
            ${sourcesHtml}
          </div>
        </div>
      `;

      // Review State Change Listener
      const select = cardEl.querySelector(`#reviewState-${card.id}`);
      select.addEventListener("change", async (e) => {
        const newState = e.target.value;
        try {
          const res = await fetch(`/api/cards/${card.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ review_state: newState }),
          });
          if (!res.ok) throw new Error("Failed to update card review state.");
          showToast(`Memory marked as ${newState}.`, "success");
        } catch (err) {
          showToast(err.message, "error");
          select.value = card.review_state;
        }
      });

      // Playback Listeners for Evidence Quotes
      const listenBtns = cardEl.querySelectorAll(".listen-passage-btn");
      listenBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          const start = parseFloat(btn.dataset.start);
          const end = parseFloat(btn.dataset.end);
          const targetBox = document.getElementById(btn.dataset.targetId);
          playAudioSegment(start, end, targetBox);
        });
      });

      el.memoryCardsList.appendChild(cardEl);
    });
  }

  // Master Audio Player Controls
  function initAudioPlayer() {
    const audio = el.mainAudioElement;
    if (!audio) return;

    audio.addEventListener("timeupdate", () => {
      const cur = audio.currentTime;
      const dur = audio.duration || 0;
      el.playerTimeDisplay.textContent = `${formatTimeSeconds(cur)} / ${formatTimeSeconds(dur)}`;
      if (dur > 0) {
        el.playerScrubBar.value = (cur / dur) * 100;
      }
    });

    audio.addEventListener("play", () => {
      el.masterPlayText.textContent = "Pause";
    });

    audio.addEventListener("pause", () => {
      el.masterPlayText.textContent = "Play";
    });

    audio.addEventListener("ended", () => {
      el.masterPlayText.textContent = "Play";
    });

    el.masterPlayPauseBtn.addEventListener("click", () => {
      if (audio.paused) {
        audio.play().catch((err) => showToast("Playback error: " + err.message, "error"));
      } else {
        audio.pause();
      }
    });

    el.playerScrubBar.addEventListener("input", (e) => {
      const percent = parseFloat(e.target.value);
      if (audio.duration) {
        audio.currentTime = (percent / 100) * audio.duration;
      }
    });

    // Speed toggle (1.0x -> 1.25x -> 1.5x -> 1.0x)
    el.playerSpeedBtn.addEventListener("click", () => {
      if (audio.playbackRate === 1.0) {
        audio.playbackRate = 1.25;
        el.playerSpeedBtn.textContent = "1.25x";
      } else if (audio.playbackRate === 1.25) {
        audio.playbackRate = 1.5;
        el.playerSpeedBtn.textContent = "1.5x";
      } else {
        audio.playbackRate = 1.0;
        el.playerSpeedBtn.textContent = "1.0x";
      }
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Phase E: Story Export
  function exportStoryZip(storyId) {
    if (!storyId) return;
    showToast("Preparing story export archive...", "info");
    const a = document.createElement("a");
    a.href = `/api/stories/${storyId}/export`;
    a.download = `echoarchive-${storyId}.zip`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 100);
  }

  // Phase E: Safe Story Deletion Dialog & Execution
  let pendingDeleteStoryId = null;
  let deleteRestoreFocusEl = null;

  function openDeleteModal(storyId, storyTitle, triggerEl = null) {
    pendingDeleteStoryId = storyId;
    deleteRestoreFocusEl = triggerEl || document.activeElement;
    if (el.deleteStoryTitleLabel) {
      el.deleteStoryTitleLabel.textContent = storyTitle ? `"${storyTitle}"` : "this story";
    }
    if (el.deleteConfirmCheckbox) {
      el.deleteConfirmCheckbox.checked = false;
    }
    if (el.confirmDeleteBtn) {
      el.confirmDeleteBtn.disabled = true;
    }
    if (el.deleteConfirmModal) {
      el.deleteConfirmModal.style.display = "flex";
      el.deleteConfirmCheckbox.focus();
    }
  }

  function closeDeleteModal() {
    pendingDeleteStoryId = null;
    if (el.deleteConfirmModal) {
      el.deleteConfirmModal.style.display = "none";
    }
    if (deleteRestoreFocusEl && typeof deleteRestoreFocusEl.focus === "function") {
      deleteRestoreFocusEl.focus();
    }
  }

  async function executeStoryDeletion() {
    if (!pendingDeleteStoryId) return;
    const storyId = pendingDeleteStoryId;
    try {
      if (el.confirmDeleteBtn) el.confirmDeleteBtn.disabled = true;
      const res = await fetch(`/api/stories/${storyId}?confirm=true`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error?.message || "Failed to delete story.");
      }
      showToast("Story and local media permanently deleted.", "success");
      closeDeleteModal();
      if (state.currentStoryId === storyId) {
        state.currentStoryId = null;
        state.currentStory = null;
        state.segments = [];
        state.memoryCards = [];
      }
      loadStoryArchive();
    } catch (err) {
      showToast(err.message, "error");
      if (el.confirmDeleteBtn) el.confirmDeleteBtn.disabled = false;
    }
  }

  // Phase E: Privacy Modal
  let privacyRestoreFocusEl = null;

  function openPrivacyModal(triggerEl = null) {
    privacyRestoreFocusEl = triggerEl || document.activeElement;
    if (el.privacyModal) {
      el.privacyModal.style.display = "flex";
      if (el.closePrivacyBtn) el.closePrivacyBtn.focus();
    }
  }

  function closePrivacyModal() {
    if (el.privacyModal) {
      el.privacyModal.style.display = "none";
    }
    if (privacyRestoreFocusEl && typeof privacyRestoreFocusEl.focus === "function") {
      privacyRestoreFocusEl.focus();
    }
  }

  // Phase E: Archive Search & Excerpt Highlighting
  let searchDebounceTimer = null;

  function highlightMatches(text, query) {
    if (!text || !query) return escapeHtml(text || "");
    const escapedText = escapeHtml(text);
    const escapedQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`(${escapedQuery})`, "gi");
    return escapedText.replace(regex, "<mark>$1</mark>");
  }

  async function handleArchiveSearch(query) {
    const q = query.trim();
    if (!q || q.length < 2) {
      if (el.searchResultsSection) el.searchResultsSection.style.display = "none";
      if (el.storiesGrid) el.storiesGrid.style.display = "grid";
      renderStoriesGrid(state.stories);
      return;
    }

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=50`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error?.message || "Search failed.");
      }
      const data = await res.json();
      renderSearchResults(data, q);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function renderSearchResults(data, query) {
    if (!el.searchResultsSection || !el.searchResultsList) return;

    el.storiesGrid.style.display = "none";
    el.archiveEmptyState.style.display = "none";
    el.searchResultsSection.style.display = "block";

    const total = data.total || 0;
    el.searchResultsHeading.textContent = `Archive Search Results (${total})`;
    el.searchResultsSub.textContent = total === 1
      ? `1 match found for "${query}"`
      : `${total} matches found across stories, transcripts, and memories for "${query}"`;

    el.searchResultsList.innerHTML = "";

    if (total === 0) {
      el.searchResultsList.innerHTML = `
        <div class="empty-state" style="padding: var(--space-xl) 0;">
          <h3 class="empty-title" style="font-size: 1.15rem;">No matches found</h3>
          <p class="empty-desc">No stories, transcript passages, or memory cards matched "${escapeHtml(query)}". Try another keyword.</p>
        </div>
      `;
      announce(`No search results found for ${query}`);
      return;
    }

    announce(`${total} search results found for ${query}`);

    data.results.forEach((result) => {
      const card = document.createElement("article");
      card.className = "search-result-card";
      card.tabIndex = 0;
      card.role = "listitem";

      let badgeHtml = "";
      let detailHtml = "";

      if (result.result_type === "story") {
        badgeHtml = `<span class="result-badge result-badge-story">Story</span>`;
        detailHtml = `
          <div class="result-title">${highlightMatches(result.story_title, query)}</div>
          <div class="result-meta-line">Narrator: ${escapeHtml(result.speaker_label || "Unknown Speaker")}</div>
        `;
      } else if (result.result_type === "transcript") {
        const timeStr = formatTimestampMs(result.start_ms);
        badgeHtml = `
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="result-badge result-badge-transcript">Spoken Transcript Passage</span>
            <span class="result-time-pill">[${timeStr}]</span>
          </div>
        `;
        detailHtml = `
          <div class="result-meta-line">Story: <strong>${escapeHtml(result.story_title)}</strong> &bull; ${escapeHtml(result.speaker_label || "Speaker")}</div>
          <div class="result-snippet">${highlightMatches(result.snippet || result.text, query)}</div>
        `;
      } else if (result.result_type === "memory") {
        const staleBadge = result.is_stale ? ` <span class="badge badge-warning" style="font-size: 0.7rem;">Stale</span>` : "";
        badgeHtml = `
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="result-badge result-badge-memory">Traceable Memory</span>
            ${staleBadge}
          </div>
        `;
        const themesHtml = (result.themes || []).map(t => `<span class="theme-tag">${escapeHtml(t)}</span>`).join(" ");
        detailHtml = `
          <div class="result-title">${highlightMatches(result.card_title, query)}</div>
          <div class="result-meta-line">Story: <strong>${escapeHtml(result.story_title)}</strong></div>
          <div class="result-snippet">${highlightMatches(result.snippet || result.summary, query)}</div>
          ${themesHtml ? `<div style="margin-top: 8px; display: flex; gap: 4px; flex-wrap: wrap;">${themesHtml}</div>` : ""}
        `;
      }

      card.innerHTML = `
        <div class="result-badge-row">
          ${badgeHtml}
          <span style="font-size: 0.75rem; color: var(--color-amber);">Open &rarr;</span>
        </div>
        ${detailHtml}
      `;

      const onSelect = () => {
        if (result.result_type === "story") {
          loadStoryWorkspace(result.story_id);
        } else if (result.result_type === "transcript") {
          loadStoryWorkspace(result.story_id).then(() => {
            setTimeout(() => {
              const segEl = document.getElementById(`seg-${result.segment_id}`);
              if (segEl) {
                segEl.scrollIntoView({ behavior: "smooth", block: "center" });
                playAudioSegment(result.start_ms / 1000, result.end_ms / 1000, segEl);
              }
            }, 350);
          });
        } else if (result.result_type === "memory") {
          loadMemoriesScreen(result.story_id);
        }
      };

      card.addEventListener("click", onSelect);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      });

      el.searchResultsList.appendChild(card);
    });
  }

  function clearSearchResults() {
    if (el.archiveSearchInput) el.archiveSearchInput.value = "";
    if (el.searchResultsSection) el.searchResultsSection.style.display = "none";
    if (el.storiesGrid) el.storiesGrid.style.display = "grid";
    renderStoriesGrid(state.stories);
  }

  // Event Listeners Binding
  function bindEventListeners() {
    // Top Nav buttons
    el.navHomeBtn.addEventListener("click", () => navigateTo("screenHome"));
    el.brandHomeLink.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo("screenHome");
    });
    el.navRecordBtn.addEventListener("click", () => navigateTo("screenRecordUpload"));
    el.navArchiveBtn.addEventListener("click", loadStoryArchive);

    // Hero Call-to-actions
    el.heroStartRecordBtn.addEventListener("click", () => {
      navigateTo("screenRecordUpload");
      el.tabRecordBtn.click();
    });
    el.heroUploadBtn.addEventListener("click", () => {
      navigateTo("screenRecordUpload");
      el.tabUploadBtn.click();
    });
    el.heroBrowseArchiveBtn.addEventListener("click", loadStoryArchive);
    el.emptyRecordBtn.addEventListener("click", () => navigateTo("screenRecordUpload"));

    // Screen 2: Tab Switching
    el.tabRecordBtn.addEventListener("click", () => {
      el.tabRecordBtn.classList.add("active");
      el.tabUploadBtn.classList.remove("active");
      el.tabRecordBtn.setAttribute("aria-selected", "true");
      el.tabUploadBtn.setAttribute("aria-selected", "false");
      el.panelRecord.style.display = "block";
      el.panelUpload.style.display = "none";
    });

    el.tabUploadBtn.addEventListener("click", () => {
      el.tabUploadBtn.classList.add("active");
      el.tabRecordBtn.classList.remove("active");
      el.tabUploadBtn.setAttribute("aria-selected", "true");
      el.tabRecordBtn.setAttribute("aria-selected", "false");
      el.panelUpload.style.display = "block";
      el.panelRecord.style.display = "none";
    });

    // Screen 2: Recording Controls
    el.startRecordBtn.addEventListener("click", startMicrophoneRecording);
    el.stopRecordBtn.addEventListener("click", stopMicrophoneRecording);
    el.replayRecordBtn.addEventListener("click", () => {
      if (el.recordedAudioPreview && state.recordedBlob) {
        el.recordedAudioPreview.play();
      }
    });
    el.discardRecordBtn.addEventListener("click", discardMicrophoneRecording);

    // Screen 2: File Upload Dropzone
    el.fileDropZone.addEventListener("click", () => el.audioFileInput.click());
    el.fileDropZone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        el.audioFileInput.click();
      }
    });

    el.audioFileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (file) handleSelectedAudioFile(file);
    });

    el.fileDropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.fileDropZone.classList.add("dragover");
    });

    el.fileDropZone.addEventListener("dragleave", () => {
      el.fileDropZone.classList.remove("dragover");
    });

    el.fileDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      el.fileDropZone.classList.remove("dragover");
      const file = e.dataTransfer.files[0];
      if (file) handleSelectedAudioFile(file);
    });

    function handleSelectedAudioFile(file) {
      if (file.size > 25 * 1024 * 1024) {
        showToast("Audio file exceeds maximum size limit of 25 MiB.", "error");
        return;
      }
      state.selectedUploadFile = file;
      el.selectedFileInfo.textContent = `Selected file: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MiB)`;
      el.selectedFileInfo.style.display = "block";
      validateIngestFormState();
    }

    // Screen 2: Form Input Listeners
    el.storyTitleInput.addEventListener("input", validateIngestFormState);
    el.consentCheckbox.addEventListener("change", validateIngestFormState);
    el.storyIngestForm.addEventListener("submit", handleStoryIngestSubmit);

    // Screen 3: Human Review Confirmation
    el.confirmReviewBtn.addEventListener("click", async () => {
      if (!state.currentStoryId) return;
      try {
        const res = await fetch(`/api/stories/${state.currentStoryId}/review`, {
          method: "POST",
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error?.message || "Failed to confirm review.");
        }
        state.currentStory.is_reviewed = true;
        showToast("Human transcript review verified and recorded.", "success");
        renderTranscriptWorkspace();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    // Screen 3: Proceed to Memory Extraction
    el.proceedToExtractBtn.addEventListener("click", triggerMemoryExtraction);

    // Screen 4: Stepper Actions
    el.cancelExtractionBtn.addEventListener("click", () => {
      if (state.jobPollTimer) clearInterval(state.jobPollTimer);
      loadStoryWorkspace(state.currentStoryId);
    });
    el.retryExtractionBtn.addEventListener("click", triggerMemoryExtraction);

    // Screen 5: Search Filter with Local Full-Text API
    if (el.archiveSearchInput) {
      el.archiveSearchInput.addEventListener("input", (e) => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
          handleArchiveSearch(e.target.value);
        }, 250);
      });
    }

    if (el.clearSearchBtn) {
      el.clearSearchBtn.addEventListener("click", clearSearchResults);
    }

    // Phase E: Modals
    if (el.navPrivacyBtn) {
      el.navPrivacyBtn.addEventListener("click", () => openPrivacyModal(el.navPrivacyBtn));
    }
    if (el.closePrivacyBtn) {
      el.closePrivacyBtn.addEventListener("click", closePrivacyModal);
    }
    if (el.cancelDeleteBtn) {
      el.cancelDeleteBtn.addEventListener("click", closeDeleteModal);
    }
    if (el.deleteConfirmCheckbox) {
      el.deleteConfirmCheckbox.addEventListener("change", (e) => {
        if (el.confirmDeleteBtn) {
          el.confirmDeleteBtn.disabled = !e.target.checked;
        }
      });
    }
    if (el.confirmDeleteBtn) {
      el.confirmDeleteBtn.addEventListener("click", executeStoryDeletion);
    }

    // Global Modal Dismissal via Escape Key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (el.deleteConfirmModal && el.deleteConfirmModal.style.display !== "none") {
          closeDeleteModal();
        }
        if (el.privacyModal && el.privacyModal.style.display !== "none") {
          closePrivacyModal();
        }
      }
    });

    // Screen 6: Navigation & Regeneration
    el.backToTranscriptBtn.addEventListener("click", () => {
      loadStoryWorkspace(state.currentStoryId);
    });
    el.regenerateMemoriesBtn.addEventListener("click", triggerMemoryExtraction);
    el.bannerRegenerateBtn.addEventListener("click", triggerMemoryExtraction);

    // Hashchange Navigation Handler
    window.addEventListener("hashchange", () => {
      handleHashNavigation();
    });
  }

  function handleHashNavigation() {
    const hash = window.location.hash;
    if (!hash || hash === "#home") {
      navigateTo("screenHome", false);
    } else if (hash === "#record") {
      navigateTo("screenRecordUpload", false);
    } else if (hash === "#archive") {
      loadStoryArchive();
    } else if (hash.startsWith("#story/")) {
      const parts = hash.split("/");
      const storyId = parts[1];
      const sub = parts[2];
      if (sub === "memories") {
        loadMemoriesScreen(storyId);
      } else if (sub === "extract") {
        state.currentStoryId = storyId;
        navigateTo("screenExtracting", false);
      } else {
        loadStoryWorkspace(storyId);
      }
    }
  }

  // App Initialization
  function initApp() {
    bindEventListeners();
    initAudioPlayer();
    checkSystemHealth();
    setInterval(checkSystemHealth, 30000);
    handleHashNavigation();
  }

  // DOM Content Loaded Launch
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
