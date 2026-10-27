"""In-process background worker and job management for EchoArchive."""

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import (
    DATA_DIR,
    MAX_QUEUED_JOBS,
    ORIGINAL_TRANSCRIPTS_DIR,
    TMP_DIR,
)
from backend.database import get_db
from backend.media import MediaValidationError, normalize_to_whisper_wav
from backend.transcription import (
    TranscriptionError,
    transcribe_audio_file,
)

logger = logging.getLogger("echoarchive.jobs")

VALID_STATUSES = {"queued", "running", "succeeded", "failed"}
VALID_STAGES = {
    "queued",
    "preparing",
    "transcribing",
    "saving",
    "succeeded",
    "failed",
    "interrupted",
}


class JobError(Exception):
    """Base exception for job processing errors."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class JobActiveError(JobError):
    """Raised when an active job already exists for the story."""
    pass


class JobQueueFullError(JobError):
    """Raised when the job queue exceeds maximum capacity."""
    pass


class StoryNotFoundError(JobError):
    """Raised when the specified story is not found."""
    pass


def recover_interrupted_jobs(db_path: Optional[Path] = None) -> int:
    """
    On startup or recovery, find any stranded jobs in 'queued' or 'running' states
    and mark them as failed with code INTERRUPTED.
    Returns the count of recovered jobs.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT id FROM jobs WHERE status IN ('queued', 'running');
            """
        )
        stranded_jobs = [row["id"] for row in cursor.fetchall()]
        if not stranded_jobs:
            return 0

        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                stage = 'interrupted',
                error_code = 'INTERRUPTED',
                error_message = 'Job was interrupted by application shutdown or server restart.',
                finished_at = ?
            WHERE status IN ('queued', 'running');
            """,
            (now_utc,)
        )
        logger.warning("Recovered %d interrupted jobs on startup.", len(stranded_jobs))
        return len(stranded_jobs)


class TranscriptionWorker:
    """
    Single-worker in-process transcription queue manager with SQLite persistence.
    Enforces maximum concurrency of 1 for heavy inference jobs.
    """

    def __init__(self, db_path: Optional[Path] = None, max_queue_size: int = MAX_QUEUED_JOBS):
        self.db_path = db_path
        self.max_queue_size = max_queue_size
        self._queue: queue.Queue[str] = queue.Queue(maxsize=max_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background worker thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="EchoArchiveTranscriptionWorker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background worker thread gracefully."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def enqueue_transcription(self, story_id: str) -> Dict[str, Any]:
        """
        Validate preconditions and queue a transcription job for a story.
        Returns job record dict.
        """
        with get_db(self.db_path) as conn:
            # 1. Verify story exists
            story = conn.execute("SELECT id, audio_relpath FROM stories WHERE id = ?", (story_id,)).fetchone()
            if not story:
                raise StoryNotFoundError("STORY_NOT_FOUND", f"Story '{story_id}' does not exist.")

            # 2. Check if an active transcription job is already queued or running for this story
            active_job = conn.execute(
                """
                SELECT id, status, stage FROM jobs
                WHERE story_id = ? AND kind = 'transcribe' AND status IN ('queued', 'running');
                """,
                (story_id,)
            ).fetchone()
            if active_job:
                raise JobActiveError(
                    "JOB_ACTIVE",
                    f"A transcription job ({active_job['id']}) is already {active_job['status']} for this story."
                )

            # 3. Check queue capacity
            if self._queue.full():
                raise JobQueueFullError(
                    "QUEUE_CAPACITY_EXCEEDED",
                    "The transcription queue is at maximum capacity. Please wait for existing jobs to complete."
                )

            # 4. Create persistent job record
            job_id = str(uuid.uuid4())
            now_utc = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO jobs (
                    id, story_id, kind, status, stage, error_code, error_message, created_at
                ) VALUES (?, ?, 'transcribe', 'queued', 'queued', NULL, NULL, ?);
                """,
                (job_id, story_id, now_utc)
            )

        # 5. Put job ID in bounded in-memory queue
        try:
            self._queue.put_nowait(job_id)
        except queue.Full:
            # Reconcile if race condition occurred
            with get_db(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE jobs SET status = 'failed', stage = 'failed',
                    error_code = 'QUEUE_CAPACITY_EXCEEDED',
                    error_message = 'The transcription queue is at capacity.',
                    finished_at = ? WHERE id = ?
                    """,
                    (datetime.now(timezone.utc).isoformat(), job_id)
                )
            raise JobQueueFullError(
                "QUEUE_CAPACITY_EXCEEDED",
                "The transcription queue is at maximum capacity. Please wait for existing jobs to complete."
            )

        return {
            "job_id": job_id,
            "story_id": story_id,
            "kind": "transcribe",
            "status": "queued",
            "stage": "queued",
        }

    def _worker_loop(self) -> None:
        """Worker loop processing jobs one by one."""
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._process_job(job_id)
            except Exception as e:
                logger.exception("Unexpected error processing job %s: %s", job_id, e)
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        """Process a single transcription job through its documented stages."""
        # 1. Transition to running -> preparing
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_db(self.db_path) as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                logger.error("Job %s not found in database.", job_id)
                return

            story_id = job["story_id"]
            story = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
            if not story:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', stage = 'failed', error_code = 'STORY_NOT_FOUND',
                        error_message = 'Associated story not found.', finished_at = ?
                    WHERE id = ?;
                    """,
                    (now_utc, job_id)
                )
                return

            conn.execute(
                """
                UPDATE jobs
                SET status = 'running', stage = 'preparing', started_at = ?
                WHERE id = ?;
                """,
                (now_utc, job_id)
            )

        # 2. Audio preparation (normalize to 16 kHz mono WAV)
        audio_path = DATA_DIR / story["audio_relpath"]
        if not audio_path.exists():
            self._fail_job(job_id, "UNSUPPORTED_AUDIO", "Original audio recording not found on disk.")
            return

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        normalized_wav_path = TMP_DIR / f"prepared_{job_id}.wav"

        try:
            normalize_to_whisper_wav(audio_path, normalized_wav_path)
        except MediaValidationError as mve:
            self._fail_job(job_id, mve.code, mve.message)
            return
        except Exception as e:
            self._fail_job(job_id, "UNSUPPORTED_AUDIO", f"Audio preparation failed: {str(e)}")
            return

        # 3. Transition to transcribing & execute whisper.cpp
        with get_db(self.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET stage = 'transcribing' WHERE id = ?;",
                (job_id,)
            )

        try:
            segments = transcribe_audio_file(normalized_wav_path)
        except TranscriptionError as te:
            self._fail_job(job_id, te.code, te.message)
            return
        except Exception as e:
            self._fail_job(job_id, "TRANSCRIBER_FAILED", f"Transcription execution failed: {str(e)}")
            return
        finally:
            if normalized_wav_path.exists():
                try:
                    normalized_wav_path.unlink()
                except OSError:
                    pass

        # 4. Transition to saving & persist segments
        with get_db(self.db_path) as conn:
            conn.execute("UPDATE jobs SET stage = 'saving' WHERE id = ?;", (job_id,))

        try:
            self._save_transcript_results(job_id, story_id, segments)
        except Exception as e:
            logger.exception("Failed to persist transcript for job %s: %s", job_id, e)
            self._fail_job(job_id, "INTERNAL_ERROR", "Failed to persist transcript segments.")

    def _save_transcript_results(self, job_id: str, story_id: str, segments: List[Any]) -> None:
        """
        Transactionally persist transcript segments, update story revision,
        preserve immutable original transcript JSON, and mark job as succeeded.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        ORIGINAL_TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        original_json_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"

        # Serialize original machine-generated transcript
        original_data = {
            "story_id": story_id,
            "transcribed_at": now_utc,
            "segment_count": len(segments),
            "segments": [
                {
                    "segment_index": seg.segment_index,
                    "start_ms": seg.start_ms,
                    "end_ms": seg.end_ms,
                    "text": seg.text,
                }
                for seg in segments
            ],
        }

        # Write immutable original transcript if not yet present
        if not original_json_path.exists():
            with open(original_json_path, "w", encoding="utf-8") as f:
                json.dump(original_data, f, indent=2)

        with get_db(self.db_path) as conn:
            # Clear any previously existing segments if this was a full re-transcribe
            conn.execute("DELETE FROM transcript_segments WHERE story_id = ?;", (story_id,))

            # Insert all segments
            for seg in segments:
                seg_id = f"seg-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO transcript_segments (
                        id, story_id, segment_index, start_ms, end_ms, text, user_edited
                    ) VALUES (?, ?, ?, ?, ?, ?, 0);
                    """,
                    (seg_id, story_id, seg.segment_index, seg.start_ms, seg.end_ms, seg.text)
                )

            # Set initial transcript_revision to 1
            conn.execute(
                """
                UPDATE stories
                SET transcript_revision = 1, updated_at = ?
                WHERE id = ?;
                """,
                (now_utc, story_id)
            )

            # Mark job succeeded
            conn.execute(
                """
                UPDATE jobs
                SET status = 'succeeded', stage = 'succeeded', finished_at = ?
                WHERE id = ?;
                """,
                (now_utc, job_id)
            )

    def _fail_job(self, job_id: str, code: str, message: str) -> None:
        """Mark a job as failed with actionable error code and sanitized message."""
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', stage = 'failed', error_code = ?, error_message = ?, finished_at = ?
                WHERE id = ?;
                """,
                (code, message, now_utc, job_id)
            )


# Default global worker instance
global_worker = TranscriptionWorker()
