"""Deterministic tests for background transcription worker, queueing, state transitions, and recovery."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import ORIGINAL_TRANSCRIPTS_DIR
from backend.database import get_db, init_db
from backend.jobs import (
    JobActiveError,
    JobQueueFullError,
    TranscriptionWorker,
    recover_interrupted_jobs,
)
from backend.media import MediaValidationError
from backend.transcription import TranscriptSegment, TranscriptionError


@pytest.fixture
def test_env(tmp_path: Path):
    """Set up an isolated test SQLite DB and worker."""
    db_file = tmp_path / "test_jobs.sqlite3"
    init_db(db_file)

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    orig_transcripts = tmp_path / "original_transcripts"
    orig_transcripts.mkdir(parents=True, exist_ok=True)

    # Insert a dummy story
    story_id = "test-story-uuid-1"
    audio_file = media_dir / f"{story_id}.wav"
    audio_file.write_bytes(b"RIFFdummywavdata")

    with get_db(db_file) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, consent_confirmed_at, audio_relpath, audio_media_type, audio_size_bytes, audio_duration_ms, transcript_revision, created_at, updated_at
            ) VALUES (?, 'Test Story', '2026-10-28T00:00:00Z', ?, 'audio/wav', 100, 3000, 0, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """,
            (story_id, f"media/{story_id}.wav")
        )

    worker = TranscriptionWorker(db_path=db_file, max_queue_size=2)
    return {
        "db_file": db_file,
        "story_id": story_id,
        "audio_file": audio_file,
        "media_dir": media_dir,
        "orig_transcripts": orig_transcripts,
        "worker": worker,
    }


def test_enqueue_transcription_and_job_active_conflict(test_env):
    """Test enqueuing a transcription job and verifying that duplicate active jobs are rejected with JOB_ACTIVE."""
    worker = test_env["worker"]
    story_id = test_env["story_id"]

    job = worker.enqueue_transcription(story_id)
    assert job["status"] == "queued"
    assert job["story_id"] == story_id

    # Attempt to enqueue second job for same story while first is active
    with pytest.raises(JobActiveError) as exc:
        worker.enqueue_transcription(story_id)
    assert exc.value.code == "JOB_ACTIVE"


def test_queue_capacity_limit(test_env):
    """Test that submitting jobs beyond max queue capacity raises QUEUE_CAPACITY_EXCEEDED."""
    db_file = test_env["db_file"]
    worker = TranscriptionWorker(db_path=db_file, max_queue_size=2)

    # Insert 3 stories
    with get_db(db_file) as conn:
        for i in (10, 20, 30):
            conn.execute(
                """
                INSERT INTO stories (
                    id, title, consent_confirmed_at, audio_relpath, audio_media_type, audio_size_bytes, created_at, updated_at
                ) VALUES (?, ?, '2026-10-28T00:00:00Z', ?, 'audio/wav', 100, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
                """,
                (f"story-{i}", f"Title {i}", f"media/story-{i}.wav")
            )

    worker.enqueue_transcription("story-10")
    worker.enqueue_transcription("story-20")

    # Third enqueue should exceed capacity (maxsize=2)
    with pytest.raises(JobQueueFullError) as exc:
        worker.enqueue_transcription("story-30")
    assert exc.value.code == "QUEUE_CAPACITY_EXCEEDED"


def test_successful_job_execution_lifecycle(test_env):
    """Test full successful lifecycle: queued -> preparing -> transcribing -> saving -> succeeded."""
    worker = test_env["worker"]
    story_id = test_env["story_id"]
    db_file = test_env["db_file"]

    mock_segments = [
        TranscriptSegment(segment_index=0, start_ms=0, end_ms=2500, text="When I was seven years old"),
        TranscriptSegment(segment_index=1, start_ms=2500, end_ms=5000, text="in Coastal Main."),
    ]

    with patch("backend.jobs.normalize_to_whisper_wav") as mock_norm, \
         patch("backend.jobs.transcribe_audio_file", return_value=mock_segments), \
         patch("backend.jobs.DATA_DIR", test_env["media_dir"].parent), \
         patch("backend.jobs.ORIGINAL_TRANSCRIPTS_DIR", test_env["orig_transcripts"]):

        # Start worker and enqueue job
        worker.start()
        try:
            job = worker.enqueue_transcription(story_id)
            job_id = job["job_id"]

            # Wait for completion
            for _ in range(100):
                with get_db(db_file) as conn:
                    row = conn.execute("SELECT status, stage FROM jobs WHERE id = ?", (job_id,)).fetchone()
                    if row and row["status"] in ("succeeded", "failed"):
                        break
                time.sleep(0.05)

            with get_db(db_file) as conn:
                final_job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                assert final_job["status"] == "succeeded"
                assert final_job["stage"] == "succeeded"
                assert final_job["error_code"] is None

                # Verify transcript segments in SQLite
                segs = conn.execute(
                    "SELECT segment_index, start_ms, end_ms, text, user_edited FROM transcript_segments WHERE story_id = ? ORDER BY segment_index ASC",
                    (story_id,)
                ).fetchall()
                assert len(segs) == 2
                assert segs[0]["text"] == "When I was seven years old"
                assert segs[1]["text"] == "in Coastal Main."
                assert segs[0]["user_edited"] == 0

                # Verify story revision incremented to 1
                story = conn.execute("SELECT transcript_revision FROM stories WHERE id = ?", (story_id,)).fetchone()
                assert story["transcript_revision"] == 1

            # Verify immutable original transcript JSON file was written
            orig_file = test_env["orig_transcripts"] / f"{story_id}.json"
            assert orig_file.exists()
            with open(orig_file, "r") as f:
                orig_json = json.load(f)
            assert orig_json["story_id"] == story_id
            assert len(orig_json["segments"]) == 2
            assert orig_json["segments"][1]["text"] == "in Coastal Main."

        finally:
            worker.stop()


def test_transcription_subprocess_failure_persists_error(test_env):
    """Test that a transcription failure marks job as failed with actionable code and does not corrupt story."""
    worker = test_env["worker"]
    story_id = test_env["story_id"]
    db_file = test_env["db_file"]

    with patch("backend.jobs.normalize_to_whisper_wav"), \
         patch("backend.jobs.transcribe_audio_file", side_effect=TranscriptionError("TRANSCRIBER_FAILED", "whisper exited code 1")), \
         patch("backend.jobs.DATA_DIR", test_env["media_dir"].parent):

        worker.start()
        try:
            job = worker.enqueue_transcription(story_id)
            job_id = job["job_id"]

            for _ in range(100):
                with get_db(db_file) as conn:
                    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
                    if row and row["status"] in ("succeeded", "failed"):
                        break
                time.sleep(0.05)

            with get_db(db_file) as conn:
                final_job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                assert final_job["status"] == "failed"
                assert final_job["stage"] == "failed"
                assert final_job["error_code"] == "TRANSCRIBER_FAILED"
                assert "whisper exited" in final_job["error_message"]

                # Ensure story and revision are preserved (still 0)
                story = conn.execute("SELECT transcript_revision FROM stories WHERE id = ?", (story_id,)).fetchone()
                assert story["transcript_revision"] == 0
        finally:
            worker.stop()


def test_transcription_timeout_persists_error(test_env):
    """Test that a transcription timeout sets error_code TRANSCRIBER_TIMEOUT."""
    worker = test_env["worker"]
    story_id = test_env["story_id"]
    db_file = test_env["db_file"]

    with patch("backend.jobs.normalize_to_whisper_wav"), \
         patch("backend.jobs.transcribe_audio_file", side_effect=TranscriptionError("TRANSCRIBER_TIMEOUT", "timed out")), \
         patch("backend.jobs.DATA_DIR", test_env["media_dir"].parent):

        worker.start()
        try:
            job = worker.enqueue_transcription(story_id)
            job_id = job["job_id"]

            for _ in range(100):
                with get_db(db_file) as conn:
                    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
                    if row and row["status"] in ("succeeded", "failed"):
                        break
                time.sleep(0.05)

            with get_db(db_file) as conn:
                final_job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                assert final_job["status"] == "failed"
                assert final_job["error_code"] == "TRANSCRIBER_TIMEOUT"
        finally:
            worker.stop()


def test_interrupted_jobs_recovery_on_startup(test_env):
    """Test that stranded 'queued' or 'running' jobs are recovered and marked as INTERRUPTED on startup."""
    db_file = test_env["db_file"]
    story_id = test_env["story_id"]

    # Insert stranded running and queued jobs
    with get_db(db_file) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at, started_at)
            VALUES ('stranded-running-1', ?, 'transcribe', 'running', 'transcribing', '2026-10-28T00:00:00Z', '2026-10-28T00:01:00Z');
            """,
            (story_id,)
        )
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at)
            VALUES ('stranded-queued-2', ?, 'transcribe', 'queued', 'queued', '2026-10-28T00:00:00Z');
            """,
            (story_id,)
        )

    recovered_count = recover_interrupted_jobs(db_file)
    assert recovered_count == 2

    with get_db(db_file) as conn:
        for job_id in ('stranded-running-1', 'stranded-queued-2'):
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            assert job["status"] == "failed"
            assert job["stage"] == "interrupted"
            assert job["error_code"] == "INTERRUPTED"
            assert "interrupted by application shutdown" in job["error_message"]
            assert job["finished_at"] is not None
