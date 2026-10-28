"""Comprehensive deterministic tests for Phase C: Traceable Memories, Grounded AI Extraction, and Playback."""

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import DATA_DIR
from backend.database import get_db, init_db
from backend.evidence import GroundedMemoryCard
from backend.extraction import ExtractionError, RawMemoryCard
from backend.jobs import TranscriptionWorker
from backend.main import app


@pytest.fixture
def phase_c_env(tmp_path: Path):
    """Set up an isolated test environment with SQLite DB, audio media, and test story."""
    db_file = tmp_path / "test_phase_c.sqlite3"
    init_db(db_file)

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    story_id = "test-story-phase-c"
    audio_file = media_dir / f"{story_id}.wav"
    # 2-second synthetic PCM audio file
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    with get_db(db_file) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, speaker_label, consent_confirmed_at, audio_relpath,
                audio_media_type, audio_size_bytes, audio_duration_ms,
                transcript_revision, transcript_reviewed_at, created_at, updated_at
            ) VALUES (?, 'Arthur Sailboat Story', 'Arthur', '2026-10-28T00:00:00Z', ?, 'audio/wav', 1024, 18600, 1, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """,
            (story_id, f"media/{story_id}.wav")
        )

        # Insert 3 transcript segments for revision 1
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES ('seg-001', ?, 0, 0, 5240, 'When I was seven years old my grandfather Arthur built a sailboat.', 0);
            """,
            (story_id,)
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES ('seg-002', ?, 1, 5240, 10820, 'Every Sunday morning in July we took the boat to the harbor.', 0);
            """,
            (story_id,)
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES ('seg-003', ?, 2, 10820, 15400, 'He always told me that patience is like trimming the sail.', 0);
            """,
            (story_id,)
        )

    worker = TranscriptionWorker(db_path=db_file, max_queue_size=5)

    return {
        "db_file": db_file,
        "story_id": story_id,
        "audio_file": audio_file,
        "media_dir": media_dir,
        "worker": worker,
    }


def test_extraction_from_ineligible_story_without_transcript(phase_c_env):
    """Test that extraction from a story with revision=0 or missing transcript is rejected."""
    worker = phase_c_env["worker"]
    db_file = phase_c_env["db_file"]

    # Insert story with revision 0 (no transcript)
    with get_db(db_file) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, consent_confirmed_at, audio_relpath, audio_media_type,
                audio_size_bytes, audio_duration_ms, transcript_revision, created_at, updated_at
            ) VALUES ('story-untranscribed', 'No Transcript', '2026-10-28T00:00:00Z', 'media/none.wav', 'audio/wav', 100, 1000, 0, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """
        )

    from backend.jobs import JobError
    with pytest.raises(JobError) as exc:
        worker.enqueue_extraction("story-untranscribed")
    assert exc.value.code == "NO_TRANSCRIPT"


def test_extraction_stale_expected_revision_rejected(phase_c_env):
    """Test that specifying an outdated expected_revision returns REVISION_CONFLICT."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]

    from backend.jobs import JobError
    # Story is currently revision 1. Requesting with expected_revision=99 should conflict.
    with pytest.raises(JobError) as exc:
        worker.enqueue_extraction(story_id, expected_revision=99)
    assert exc.value.code == "REVISION_CONFLICT"


def test_successful_grounded_memory_extraction_lifecycle(phase_c_env):
    """Test end-to-end extraction lifecycle: queued -> preparing -> extracting -> validating -> saving -> succeeded."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    mock_raw_cards = [
        RawMemoryCard(
            title="Building a Wooden Sailboat",
            summary="Grandfather Arthur built a sailboat and took it to the harbor every Sunday.",
            themes=["tradition", "boatbuilding"],
            source_segment_ids=["seg-001", "seg-002"],
        ),
        RawMemoryCard(
            title="Sailing Wisdom",
            summary='He advised that "patience is like trimming the sail" when guiding the boat.',
            themes=["wisdom", "patience"],
            source_segment_ids=["seg-003"],
        ),
    ]

    with patch("backend.jobs.extract_memories_from_segments", return_value=mock_raw_cards):
        job_info = worker.enqueue_extraction(story_id, expected_revision=1)
        job_id = job_info["job_id"]

        # Run worker processing directly
        worker._process_job(job_id)

    with get_db(db_file) as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert job["status"] == "succeeded"
        assert job["stage"] == "succeeded"

        # Verify memory cards persisted in SQLite
        cards = conn.execute("SELECT * FROM memory_cards WHERE story_id = ? ORDER BY created_at ASC", (story_id,)).fetchall()
        assert len(cards) == 2

        card1 = cards[0]
        assert card1["title"] == "Building a Wooden Sailboat"
        assert card1["generated_from_revision"] == 1
        assert card1["review_state"] == "draft"  # Default requires human review
        assert card1["model_provenance"] == "qwen2.5:1.5b"

        # Verify sources in memory_sources
        sources1 = conn.execute("SELECT segment_id FROM memory_sources WHERE card_id = ? ORDER BY segment_id ASC", (card1["id"],)).fetchall()
        assert [s["segment_id"] for s in sources1] == ["seg-001", "seg-002"]

        card2 = cards[1]
        assert card2["title"] == "Sailing Wisdom"
        sources2 = conn.execute("SELECT segment_id FROM memory_sources WHERE card_id = ?", (card2["id"],)).fetchall()
        assert [s["segment_id"] for s in sources2] == ["seg-003"]


def test_extraction_rejects_hallucinated_direct_quote(phase_c_env):
    """Test that a model card containing an invented quotation fails validation and aborts saving."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    # Fabricated quotation not in transcript
    mock_bad_cards = [
        RawMemoryCard(
            title="Invented Quote Card",
            summary='Grandfather said "We will conquer the dark northern ocean with steel sails!"',
            themes=["invention"],
            source_segment_ids=["seg-001"],
        )
    ]

    with patch("backend.jobs.extract_memories_from_segments", return_value=mock_bad_cards):
        job_info = worker.enqueue_extraction(story_id)
        job_id = job_info["job_id"]
        worker._process_job(job_id)

    with get_db(db_file) as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert job["status"] == "failed"
        assert job["error_code"] == "UNSUPPORTED_QUOTE"

        # Assert no partial memory cards were persisted
        card_count = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0]
        assert card_count == 0


def test_extraction_rejects_nonexistent_or_cross_story_source_ids(phase_c_env):
    """Test that citing nonexistent or cross-story segment IDs fails evidence validation."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    mock_bad_cards = [
        RawMemoryCard(
            title="Cross-Story Citation",
            summary="A memory citing another story.",
            themes=["error"],
            source_segment_ids=["seg-999-cross-story"],
        )
    ]

    with patch("backend.jobs.extract_memories_from_segments", return_value=mock_bad_cards):
        job_info = worker.enqueue_extraction(story_id)
        job_id = job_info["job_id"]
        worker._process_job(job_id)

    with get_db(db_file) as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert job["status"] == "failed"
        assert job["error_code"] == "INVALID_EVIDENCE"

        card_count = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0]
        assert card_count == 0


def test_ollama_offline_or_timeout_handling_in_worker(phase_c_env):
    """Test that Ollama connection failure or timeout transitions job to failed with clean code."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    # 1. Test OLLAMA_UNAVAILABLE
    with patch(
        "backend.jobs.extract_memories_from_segments",
        side_effect=ExtractionError("OLLAMA_UNAVAILABLE", "Ollama is not running locally.")
    ):
        job1 = worker.enqueue_extraction(story_id)
        worker._process_job(job1["job_id"])

    with get_db(db_file) as conn:
        j1 = conn.execute("SELECT * FROM jobs WHERE id = ?", (job1["job_id"],)).fetchone()
        assert j1["status"] == "failed"
        assert j1["error_code"] == "OLLAMA_UNAVAILABLE"

    # 2. Test OLLAMA_TIMEOUT
    with patch(
        "backend.jobs.extract_memories_from_segments",
        side_effect=ExtractionError("OLLAMA_TIMEOUT", "Ollama request timed out after 60s.")
    ):
        job2 = worker.enqueue_extraction(story_id)
        worker._process_job(job2["job_id"])

    with get_db(db_file) as conn:
        j2 = conn.execute("SELECT * FROM jobs WHERE id = ?", (job2["job_id"],)).fetchone()
        assert j2["status"] == "failed"
        assert j2["error_code"] == "OLLAMA_TIMEOUT"


def test_transcript_edit_during_inference_triggers_revision_conflict(phase_c_env):
    """
    Test race condition: User corrects transcript while extraction inference is running.
    The worker must reject the stale extraction result at persistence time with REVISION_CONFLICT.
    """
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    inference_event = threading.Event()
    edit_done_event = threading.Event()

    def mock_extract(segments):
        # Signal that extraction is running
        inference_event.set()
        # Wait until transcript is edited in database
        edit_done_event.wait(timeout=5.0)
        return [
            RawMemoryCard(
                title="Stale Card",
                summary="Generated against revision 1 words.",
                themes=["race"],
                source_segment_ids=["seg-001"],
            )
        ]

    with patch("backend.jobs.extract_memories_from_segments", side_effect=mock_extract):
        job_info = worker.enqueue_extraction(story_id, expected_revision=1)
        job_id = job_info["job_id"]

        # Run extraction in a separate thread
        worker_thread = threading.Thread(target=worker._process_job, args=(job_id,))
        worker_thread.start()

        # Wait for inference to start
        assert inference_event.wait(timeout=3.0)

        # Simulate user editing transcript segment (incrementing revision from 1 to 2)
        with get_db(db_file) as conn:
            conn.execute(
                "UPDATE stories SET transcript_revision = 2, updated_at = '2026-10-28T01:00:00Z' WHERE id = ?;",
                (story_id,)
            )
            conn.execute(
                "UPDATE transcript_segments SET text = 'Corrected words', user_edited = 1 WHERE id = 'seg-001';"
            )

        # Release worker thread
        edit_done_event.set()
        worker_thread.join(timeout=5.0)

    with get_db(db_file) as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        assert job["status"] == "failed"
        assert job["error_code"] == "REVISION_CONFLICT"
        assert "Transcript revision changed" in job["error_message"]

        # Confirm no stale cards were persisted
        card_count = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0]
        assert card_count == 0


def test_stale_memory_flag_and_regeneration(phase_c_env):
    """
    Test:
    1. Memory cards are saved for Revision 1.
    2. User edits transcript, incrementing revision to 2.
    3. Existing cards are reported as is_stale=True.
    4. Regeneration for Revision 2 replaces stale cards and resets is_stale=False without duplicates.
    """
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    mock_rev1_cards = [
        RawMemoryCard(
            title="Initial Revision 1 Memory",
            summary="Story from initial transcription.",
            themes=["rev1"],
            source_segment_ids=["seg-001"],
        )
    ]

    # Step 1: Generate for revision 1
    with patch("backend.jobs.extract_memories_from_segments", return_value=mock_rev1_cards):
        job1 = worker.enqueue_extraction(story_id)
        worker._process_job(job1["job_id"])

    # Step 2: Simulate human edit (Revision 1 -> Revision 2)
    with get_db(db_file) as conn:
        conn.execute("UPDATE stories SET transcript_revision = 2 WHERE id = ?;", (story_id,))

    # Step 3: Check cards via FastAPI TestClient
    with patch("backend.main.get_db", lambda: get_db(db_file)):
        client = TestClient(app)
        resp = client.get(f"/api/stories/{story_id}/cards")
        assert resp.status_code == 200
        data = resp.json()

        assert data["current_transcript_revision"] == 2
        assert data["has_stale_cards"] is True
        assert len(data["cards"]) == 1

        card = data["cards"][0]
        assert card["is_stale"] is True
        assert card["generated_from_revision"] == 1
        assert "Transcript has been modified" in card["stale_reason"]

        # Step 4: Confirm review of revision 2 and regenerate
        with get_db(db_file) as conn:
            conn.execute("UPDATE stories SET transcript_reviewed_at = '2026-10-28T00:01:00Z' WHERE id = ?;", (story_id,))

        mock_rev2_cards = [
            RawMemoryCard(
                title="Updated Revision 2 Memory",
                summary="Story after transcript review and correction.",
                themes=["rev2"],
                source_segment_ids=["seg-001", "seg-002"],
            )
        ]

        with patch("backend.jobs.extract_memories_from_segments", return_value=mock_rev2_cards):
            job2 = worker.enqueue_extraction(story_id, expected_revision=2)
            worker._process_job(job2["job_id"])

        resp2 = client.get(f"/api/stories/{story_id}/cards")
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data2["current_transcript_revision"] == 2
        assert data2["has_stale_cards"] is False
        assert len(data2["cards"]) == 1  # No duplicate cards!
        card2 = data2["cards"][0]
        assert card2["title"] == "Updated Revision 2 Memory"
        assert card2["is_stale"] is False
        assert card2["generated_from_revision"] == 2
        assert len(card2["sources"]) == 2


def test_card_details_and_sources_api_endpoints(phase_c_env):
    """Test GET /api/cards/{id}, GET /api/cards/{id}/sources, and PATCH /api/cards/{id}."""
    worker = phase_c_env["worker"]
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]

    mock_cards = [
        RawMemoryCard(
            title="Arthur Workshop",
            summary="Arthur built the boat in his workshop.",
            themes=["workshop", "craftsmanship"],
            source_segment_ids=["seg-001"],
        )
    ]

    with patch("backend.jobs.extract_memories_from_segments", return_value=mock_cards):
        job = worker.enqueue_extraction(story_id)
        worker._process_job(job["job_id"])

    with patch("backend.main.get_db", lambda: get_db(db_file)):
        client = TestClient(app)

        # 1. Get cards list
        list_resp = client.get(f"/api/stories/{story_id}/cards")
        card_id = list_resp.json()["cards"][0]["id"]

        # 2. Get card details
        detail_resp = client.get(f"/api/cards/{card_id}")
        assert detail_resp.status_code == 200
        card_data = detail_resp.json()
        assert card_data["id"] == card_id
        assert card_data["title"] == "Arthur Workshop"
        assert card_data["review_state"] == "draft"
        assert card_data["model_provenance"] == "qwen2.5:1.5b"
        assert len(card_data["sources"]) == 1

        source = card_data["sources"][0]
        assert source["segment_id"] == "seg-001"
        assert source["start_seconds"] == 0.0
        assert source["end_seconds"] == 5.24
        assert source["duration_seconds"] == 5.24
        assert source["timing_reliable"] is True
        assert source["audio_url"] == f"/api/stories/{story_id}/audio"

        # 3. Get card sources endpoint
        src_resp = client.get(f"/api/cards/{card_id}/sources")
        assert src_resp.status_code == 200
        assert src_resp.json()["sources"][0]["segment_id"] == "seg-001"

        # 4. Update review state via PATCH
        patch_resp = client.patch(f"/api/cards/{card_id}", json={"review_state": "accepted"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["review_state"] == "accepted"

        # 5. Invalid review state rejected
        bad_patch = client.patch(f"/api/cards/{card_id}", json={"review_state": "hallucinated_state"})
        assert bad_patch.status_code == 422


def test_audio_playback_byte_range_and_timing_safety(phase_c_env):
    """Test that source-linked audio can be fetched and seeked via byte ranges safely."""
    story_id = phase_c_env["story_id"]
    db_file = phase_c_env["db_file"]
    media_dir = phase_c_env["media_dir"]
    data_dir = media_dir.parent

    with patch("backend.main.get_db", lambda: get_db(db_file)), \
         patch("backend.main.DATA_DIR", data_dir), \
         patch("backend.main.MEDIA_DIR", media_dir):
        client = TestClient(app)

        # Standard playback
        resp = client.get(f"/api/stories/{story_id}/audio")
        assert resp.status_code == 200
        assert resp.headers.get("accept-ranges") == "bytes"

        # Range seek playback (e.g. range 0-10)
        range_resp = client.get(f"/api/stories/{story_id}/audio", headers={"Range": "bytes=0-10"})
        assert range_resp.status_code == 206
        assert "bytes 0-10/" in range_resp.headers.get("content-range", "")
        assert len(range_resp.content) == 11

        # Nonexistent story returns 404
        missing_resp = client.get("/api/stories/nonexistent-story-id/audio")
        assert missing_resp.status_code == 404


def test_phase_c_demo_harness_endpoint():
    """Test that /demo and /phase-c-demo return the demonstration HTML harness."""
    client = TestClient(app)
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Traceable Memories Demonstration" in resp.text
