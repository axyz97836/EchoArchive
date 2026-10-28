"""Comprehensive Phase F test suite: Hardened Review Enforcement, Interruption-Safe Deletion & Export Integrity."""

import io
import json
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import DATA_DIR, MEDIA_DIR, ORIGINAL_TRANSCRIPTS_DIR, TMP_DIR
from backend.database import get_db, init_db, recover_pending_deletions
from backend.export import ExportError, build_story_export_zip, generate_offline_html
from backend.extraction import RawMemoryCard
from backend.jobs import JobError, TranscriptionWorker
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_phase_f_test_directories():
    """Ensure clean directories and up-to-date database schema before tests."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ORIGINAL_TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


def _create_story_fixture(
    story_id: str,
    title: str = "Test Story for Phase F",
    speaker: str = "Harriet Tubman",
    reviewed: bool = False,
    transcript_revision: int = 1,
) -> Path:
    """Helper to populate a synthetic story with audio, segments, and cards."""
    audio_file = MEDIA_DIR / f"{story_id}.wav"
    audio_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    audio_file.write_bytes(audio_content)

    now_utc = datetime.now(timezone.utc).isoformat()
    reviewed_at = now_utc if reviewed else None

    with get_db() as conn:
        conn.execute("DELETE FROM stories WHERE id = ?;", (story_id,))
        conn.execute(
            """
            INSERT INTO stories (
                id, title, speaker_label, consent_confirmed_at, audio_relpath,
                audio_media_type, audio_size_bytes, audio_duration_ms,
                transcript_revision, transcript_reviewed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'audio/wav', ?, 12000, ?, ?, ?, ?);
            """,
            (
                story_id,
                title,
                speaker,
                now_utc,
                f"media/{story_id}.wav",
                len(audio_content),
                transcript_revision,
                reviewed_at,
                now_utc,
                now_utc,
            ),
        )

        # Insert segments
        seg1_id = f"seg-1-{uuid.uuid4().hex[:8]}"
        seg2_id = f"seg-2-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 0, 1000, 5000, 'I had reasoned this out in my mind, there was one of two things I had a right to.', 0);
            """,
            (seg1_id, story_id),
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 1, 5200, 9800, 'Liberty or death; if I could not have one, I would have the other.', 0);
            """,
            (seg2_id, story_id),
        )

        # Insert an original transcript snapshot
        orig_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"
        orig_data = {
            "story_id": story_id,
            "transcribed_at": now_utc,
            "segment_count": 2,
            "segments": [
                {"segment_index": 0, "start_ms": 1000, "end_ms": 5000, "text": "Segment 1 original text"},
                {"segment_index": 1, "start_ms": 5200, "end_ms": 9800, "text": "Segment 2 original text"},
            ],
        }
        orig_path.write_text(json.dumps(orig_data), encoding="utf-8")

        # Insert sample memory card
        card_id = f"card-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """
            INSERT INTO memory_cards (
                id, story_id, title, summary, themes_json,
                generated_from_revision, review_state, model_provenance, created_at
            ) VALUES (?, ?, 'The Choice of Liberty', 'The narrator reflects on the fundamental right to freedom or death.', '["freedom","determination"]', ?, 'draft', 'qwen2.5:1.5b', ?);
            """,
            (card_id, story_id, transcript_revision, now_utc),
        )
        conn.execute(
            "INSERT INTO memory_sources (card_id, segment_id) VALUES (?, ?);",
            (card_id, seg1_id),
        )

    return audio_file


# ==============================================================================
# SECTION A: Hardened Transcript Review Semantics & Bypass Prevention
# ==============================================================================


def test_normal_extraction_rejects_unreviewed_transcript():
    """POST /api/stories/{id}/extract rejects unreviewed transcripts even with empty or missing payload."""
    story_id = f"pf-unreviewed-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, reviewed=False)

    # Empty body
    resp = client.post(f"/api/stories/{story_id}/extract", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REVIEW_REQUIRED"

    # No payload at all
    resp_no_body = client.post(f"/api/stories/{story_id}/extract")
    assert resp_no_body.status_code == 422
    assert resp_no_body.json()["error"]["code"] == "REVIEW_REQUIRED"


def test_extraction_rejects_public_bypass_attempt():
    """POST /api/stories/{id}/extract with require_review=False is explicitly rejected with 422 REVIEW_BYPASS_FORBIDDEN."""
    story_id = f"pf-bypass-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, reviewed=False)

    resp = client.post(
        f"/api/stories/{story_id}/extract",
        json={"expected_revision": 1, "require_review": False},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REVIEW_BYPASS_FORBIDDEN"
    assert "Bypassing transcript review is forbidden" in resp.json()["error"]["message"]


def test_extraction_succeeds_after_explicit_human_review():
    """Once a user explicitly confirms transcript review, extraction is queued successfully."""
    story_id = f"pf-reviewed-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, reviewed=False)

    # Initial extraction rejected
    resp1 = client.post(f"/api/stories/{story_id}/extract")
    assert resp1.status_code == 422
    assert resp1.json()["error"]["code"] == "REVIEW_REQUIRED"

    # Confirm review explicitly
    rev_resp = client.post(f"/api/stories/{story_id}/review")
    assert rev_resp.status_code == 200
    assert rev_resp.json()["is_reviewed"] is True
    assert rev_resp.json()["transcript_reviewed_at"] is not None

    # Now extraction is accepted (202)
    resp2 = client.post(f"/api/stories/{story_id}/extract")
    assert resp2.status_code == 202
    assert resp2.json()["status"] == "queued"
    assert resp2.json()["kind"] == "extract"


def test_transcript_edit_invalidates_review_and_blocks_extraction():
    """Editing any transcript segment resets transcript_reviewed_at to NULL and blocks extraction until re-reviewed."""
    story_id = f"pf-edit-inval-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, reviewed=True, transcript_revision=1)

    # Initially reviewed, extraction accepted
    story_data = client.get(f"/api/stories/{story_id}").json()
    assert story_data["is_reviewed"] is True
    assert story_data["transcript_reviewed_at"] is not None

    # Get segment to edit
    segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
    target_seg_id = segs[0]["id"]

    # Human edits a segment
    patch_resp = client.patch(
        f"/api/stories/{story_id}/segments/{target_seg_id}",
        json={"text": "Corrected wording during review.", "expected_revision": 1},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["transcript_revision"] == 2
    assert patch_resp.json()["transcript_reviewed_at"] is None

    # Story is now unreviewed
    story_data2 = client.get(f"/api/stories/{story_id}").json()
    assert story_data2["is_reviewed"] is False
    assert story_data2["transcript_reviewed_at"] is None
    assert story_data2["transcript_revision"] == 2

    # Extraction must be rejected
    extract_resp = client.post(f"/api/stories/{story_id}/extract")
    assert extract_resp.status_code == 422
    assert extract_resp.json()["error"]["code"] == "REVIEW_REQUIRED"

    # Existing memory card is now marked stale
    cards_data = client.get(f"/api/stories/{story_id}/cards").json()
    assert cards_data["has_stale_cards"] is True
    assert cards_data["cards"][0]["is_stale"] is True

    # User re-reviews revision 2
    review2_resp = client.post(f"/api/stories/{story_id}/review")
    assert review2_resp.status_code == 200
    assert review2_resp.json()["is_reviewed"] is True
    assert review2_resp.json()["transcript_revision"] == 2

    # Now extraction is accepted again for revision 2
    extract_resp2 = client.post(
        f"/api/stories/{story_id}/extract",
        json={"expected_revision": 2},
    )
    assert extract_resp2.status_code == 202


# ==============================================================================
# SECTION B: Safe Deletion, Interruption Journal & Concurrency Barrier
# ==============================================================================


def test_deletion_requires_explicit_confirmation():
    """DELETE /api/stories/{id} rejects unconfirmed requests with 422 CONFIRMATION_REQUIRED."""
    story_id = f"pf-del-unconf-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id)

    # Without confirmation query or body
    resp = client.delete(f"/api/stories/{story_id}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    # With confirm=false
    resp2 = client.delete(f"/api/stories/{story_id}?confirm=false")
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_deletion_rejects_active_jobs():
    """DELETE /api/stories/{id} returns 409 JOB_ACTIVE if a job is actively running."""
    story_id = f"pf-del-active-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id)

    job_id = f"job-del-active-{uuid.uuid4().hex[:8]}"
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at)
            VALUES (?, ?, 'transcribe', 'running', 'transcribing', ?);
            """,
            (job_id, story_id, now_utc),
        )

    resp = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ACTIVE"


def test_successful_deletion_cleans_db_files_and_journal():
    """Successful deletion removes database rows, unlinks audio and transcripts, and leaves journal clean."""
    story_id = f"pf-del-clean-{uuid.uuid4().hex[:8]}"
    audio_path = _create_story_fixture(story_id)
    transcript_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"

    assert audio_path.exists()
    assert transcript_path.exists()

    resp = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Filesystem must be purged
    assert not audio_path.exists()
    assert not transcript_path.exists()

    # Database story and child records must be cascade deleted
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM stories WHERE id = ?;", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0
        # Deletion journal must be clean
        assert conn.execute("SELECT COUNT(*) FROM deletion_journal WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0


def test_deletion_preserves_unrelated_stories():
    """Deleting story A does not touch story B, its audio, or its transcripts."""
    story_a = f"pf-del-iso-a-{uuid.uuid4().hex[:8]}"
    story_b = f"pf-del-iso-b-{uuid.uuid4().hex[:8]}"

    audio_a = _create_story_fixture(story_a, title="Story A")
    audio_b = _create_story_fixture(story_b, title="Story B")

    assert audio_a.exists()
    assert audio_b.exists()

    # Delete Story A
    resp = client.delete(f"/api/stories/{story_a}?confirm=true")
    assert resp.status_code == 200

    # Story A gone
    assert not audio_a.exists()
    assert client.get(f"/api/stories/{story_a}").status_code == 404

    # Story B intact
    assert audio_b.exists()
    assert client.get(f"/api/stories/{story_b}").status_code == 200
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM stories WHERE id = ?;", (story_b,)).fetchone()[0] == 1


def test_interrupted_deletion_journal_recovery():
    """Simulate an interrupted deletion where files were recorded in deletion_journal. recover_pending_deletions purges them."""
    story_id = f"pf-del-interrupted-{uuid.uuid4().hex[:8]}"
    audio_path = MEDIA_DIR / f"{story_id}.wav"
    audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    transcript_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"
    transcript_path.write_text('{"mock": "data"}', encoding="utf-8")

    journal_id = f"del-mock-{uuid.uuid4().hex[:8]}"
    now_utc = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO deletion_journal (id, story_id, audio_relpath, original_transcript_path, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (journal_id, story_id, f"media/{story_id}.wav", str(transcript_path), now_utc),
        )

    assert audio_path.exists()
    assert transcript_path.exists()

    # Recover pending deletions
    recovered = recover_pending_deletions()
    assert story_id in recovered

    # Files must now be unlinked
    assert not audio_path.exists()
    assert not transcript_path.exists()

    # Journal row must be cleared
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM deletion_journal WHERE id = ?;", (journal_id,)).fetchone()[0] == 0


def test_repeated_deletion_on_journaled_entry():
    """Repeated DELETE on an incomplete deletion retries journaled cleanup and returns 200 once complete."""
    story_id = f"pf-del-retry-{uuid.uuid4().hex[:8]}"
    audio_path = MEDIA_DIR / f"{story_id}.wav"
    audio_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    journal_id = f"del-retry-{uuid.uuid4().hex[:8]}"
    now_utc = datetime.now(timezone.utc).isoformat()

    # Insert into journal without story existing in stories (simulating crash after DB delete)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO deletion_journal (id, story_id, audio_relpath, original_transcript_path, created_at)
            VALUES (?, ?, ?, NULL, ?);
            """,
            (journal_id, story_id, f"media/{story_id}.wav", now_utc),
        )

    # Calling DELETE again should detect journal entry, complete cleanup, and return 200
    resp = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp.status_code == 200
    assert not audio_path.exists()

    # Calling DELETE a third time now returns 404 (fully cleaned)
    resp3 = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp3.status_code == 404


# ==============================================================================
# SECTION C: Portable ZIP Export Audit
# ==============================================================================


def test_export_preserves_exact_audio_bytes_and_sha256_checksum():
    """Exported ZIP contains identical original audio bytes matching SHA-256 hash in manifest.json."""
    story_id = f"pf-export-audit-{uuid.uuid4().hex[:8]}"
    audio_path = _create_story_fixture(story_id)
    original_bytes = audio_path.read_bytes()

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    namelist = zf.namelist()

    assert "audio.wav" in namelist
    assert "manifest.json" in namelist
    assert "story.json" in namelist
    assert "transcript.json" in namelist
    assert "memories.json" in namelist
    assert "story.html" in namelist

    # Verify identical bytes
    exported_audio = zf.read("audio.wav")
    assert exported_audio == original_bytes

    # Verify manifest hash
    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["format"] == "echoarchive-export-v1"
    audio_entry = next(f for f in manifest["files"] if f["path"] == "audio.wav")
    assert audio_entry["size_bytes"] == len(original_bytes)
    import hashlib
    expected_sha256 = hashlib.sha256(original_bytes).hexdigest()
    assert audio_entry["sha256"] == expected_sha256


def test_export_html_reader_is_offline_and_escaped():
    """Offline HTML reader operates with zero external dependencies and labels cards as AI Interpretations."""
    story_id = f"pf-export-html-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, title="Dangerous <script>alert(1)</script> Story")

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    html_content = zf.read("story.html").decode("utf-8")

    # Script tag must be escaped
    assert "<script>alert(1)</script>" not in html_content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_content

    # Zero remote CDN or web font references
    assert "http://" not in html_content
    assert "https://" not in html_content
    assert "<script" not in html_content.lower()

    # AI interpretation label
    assert "AI Interpretation" in html_content
    assert "Interpretive summaries generated by local AI" in html_content


def test_export_rejects_active_job():
    """Export returns 409 JOB_ACTIVE if a transcription or extraction job is in progress."""
    story_id = f"pf-export-busy-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id)

    job_id = f"job-exp-busy-{uuid.uuid4().hex[:8]}"
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at)
            VALUES (?, ?, 'extract', 'running', 'extracting', ?);
            """,
            (job_id, story_id, now_utc),
        )

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ACTIVE"


def test_export_detects_concurrent_revision_modification():
    """If the story revision changes concurrently while generating export, REVISION_CONFLICT is raised."""
    story_id = f"pf-export-rev-conflict-{uuid.uuid4().hex[:8]}"
    _create_story_fixture(story_id, transcript_revision=1)

    with get_db() as real_conn:
        class ConcurrentEditConn:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, sql, *args):
                if "SELECT transcript_revision FROM stories" in sql:
                    # Simulate concurrent edit bumping revision
                    self._conn.execute("UPDATE stories SET transcript_revision = 9 WHERE id = ?;", (story_id,))
                return self._conn.execute(sql, *args)

            def __getattr__(self, item):
                return getattr(self._conn, item)

        wrapper_conn = ConcurrentEditConn(real_conn)
        with pytest.raises(ExportError) as exc:
            build_story_export_zip(wrapper_conn, story_id)
        assert exc.value.code == "REVISION_CONFLICT"
