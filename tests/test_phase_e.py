"""Comprehensive Phase E test suite: Search, Portable Export, Safe Deletion & Review Semantics."""

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
from backend.database import get_db, init_db
from backend.export import build_story_export_zip, generate_offline_html
from backend.jobs import JobError, TranscriptionWorker
from backend.main import app
from backend.search import extract_snippet, search_archive

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_directories():
    """Ensure clean directories before tests."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ORIGINAL_TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    yield


def _create_test_story_fixture(
    db_path: Path,
    story_id: str,
    title: str = "A Story About Courtyard Marigolds",
    speaker: str = "Elena Rostova",
    reviewed: bool = False,
    transcript_revision: int = 1,
) -> Path:
    """Helper to populate a synthetic story with audio, segments, and cards."""
    # Write synthetic audio
    audio_file = MEDIA_DIR / f"{story_id}.wav"
    audio_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    audio_file.write_bytes(audio_content)

    now_utc = datetime.now(timezone.utc).isoformat()
    reviewed_at = now_utc if reviewed else None

    with get_db(db_path) as conn:
        conn.execute("DELETE FROM stories WHERE id = ? OR audio_relpath = ?;", (story_id, f"media/{story_id}.wav"))
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
        uid = uuid.uuid4().hex[:10]
        seg1_id = f"seg-1-{uid}"
        seg2_id = f"seg-2-{uid}"
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 0, 1000, 5000, 'When I was young, we planted golden marigolds by the courtyard.', 0);
            """,
            (seg1_id, story_id),
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 1, 5200, 9800, 'Every autumn my grandmother showed me which seeds to preserve for spring.', 0);
            """,
            (seg2_id, story_id),
        )

        # Insert memory card
        card_id = f"card-1-{uid}"
        conn.execute(
            """
            INSERT INTO memory_cards (
                id, story_id, title, summary, themes_json,
                generated_from_revision, review_state, model_provenance, created_at
            ) VALUES (?, ?, 'Marigold Planting Tradition', 'Memories of planting marigolds with grandmother.', '["gardening", "family tradition", "heritage"]', ?, 'draft', 'qwen2.5:1.5b', ?);
            """,
            (card_id, story_id, transcript_revision, now_utc),
        )

        conn.execute(
            "INSERT INTO memory_sources (card_id, segment_id) VALUES (?, ?);",
            (card_id, seg1_id),
        )
        conn.execute(
            "INSERT INTO memory_sources (card_id, segment_id) VALUES (?, ?);",
            (card_id, seg2_id),
        )

        # Write original machine transcript snapshot
        orig_transcript_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"
        orig_data = {
            "story_id": story_id,
            "transcribed_at": now_utc,
            "segments": [
                {"segment_index": 0, "start_ms": 1000, "end_ms": 5000, "text": "When I was young, we planted golden marigolds by the courtyard."},
                {"segment_index": 1, "start_ms": 5200, "end_ms": 9800, "text": "Every autumn my grandmother showed me which seeds to preserve for spring."},
            ],
        }
        orig_transcript_path.write_text(json.dumps(orig_data), encoding="utf-8")

    return audio_file


# ==============================================================================
# 1. Transcript Review Semantics & Stale Memory Acceptance Tests
# ==============================================================================


def test_initial_machine_transcript_requires_review(tmp_path):
    """Initial transcript has transcript_reviewed_at = None and is_reviewed = False."""
    story_id = "test-review-initial-001"
    _create_test_story_fixture(None, story_id, reviewed=False)

    resp = client.get(f"/api/stories/{story_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_reviewed"] is False
    assert data["transcript_reviewed_at"] is None


def test_editing_segment_does_not_approve_transcript():
    """Editing a segment must increment revision and keep or reset transcript_reviewed_at to NULL."""
    story_id = "test-review-edit-002"
    _create_test_story_fixture(None, story_id, reviewed=False, transcript_revision=1)

    # Get segment id
    segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
    seg_id = segs[0]["id"]

    # Patch segment
    patch_resp = client.patch(
        f"/api/stories/{story_id}/segments/{seg_id}",
        json={"text": "When I was very young, we planted golden marigolds.", "expected_revision": 1},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["transcript_revision"] == 2
    assert patch_resp.json()["transcript_reviewed_at"] is None

    # Story record verification
    story_resp = client.get(f"/api/stories/{story_id}").json()
    assert story_resp["transcript_revision"] == 2
    assert story_resp["is_reviewed"] is False
    assert story_resp["transcript_reviewed_at"] is None


def test_explicit_review_confirms_current_revision():
    """POST /api/stories/{id}/review confirms human review."""
    story_id = "test-review-confirm-003"
    _create_test_story_fixture(None, story_id, reviewed=False)

    rev_resp = client.post(f"/api/stories/{story_id}/review")
    assert rev_resp.status_code == 200
    assert rev_resp.json()["is_reviewed"] is True
    assert rev_resp.json()["transcript_reviewed_at"] is not None

    story_resp = client.get(f"/api/stories/{story_id}").json()
    assert story_resp["is_reviewed"] is True


def test_editing_confirmed_transcript_invalidates_review():
    """If a previously confirmed transcript is edited, its review confirmation is invalidated."""
    story_id = "test-review-invalidate-004"
    _create_test_story_fixture(None, story_id, reviewed=True, transcript_revision=1)

    # Verify initially reviewed
    init_story = client.get(f"/api/stories/{story_id}").json()
    assert init_story["is_reviewed"] is True
    assert init_story["transcript_reviewed_at"] is not None

    # Edit segment
    segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
    seg_id = segs[0]["id"]
    patch_resp = client.patch(
        f"/api/stories/{story_id}/segments/{seg_id}",
        json={"text": "A newly corrected segment text.", "expected_revision": 1},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["transcript_reviewed_at"] is None

    # Re-fetch story: review must be invalidated
    updated_story = client.get(f"/api/stories/{story_id}").json()
    assert updated_story["is_reviewed"] is False
    assert updated_story["transcript_reviewed_at"] is None
    assert updated_story["transcript_revision"] == 2


def test_extraction_rejects_unreviewed_when_require_review_is_true():
    """POST /api/stories/{id}/extract rejects unreviewed stories if require_review=True."""
    story_id = "test-review-require-005"
    _create_test_story_fixture(None, story_id, reviewed=False, transcript_revision=1)

    resp = client.post(
        f"/api/stories/{story_id}/extract",
        json={"expected_revision": 1, "require_review": True},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REVIEW_REQUIRED"


def test_cannot_accept_stale_memory_card():
    """PATCH /api/cards/{id} with review_state='accepted' rejects stale memory cards (409)."""
    story_id = "test-review-stale-card-006"
    _create_test_story_fixture(None, story_id, reviewed=True, transcript_revision=1)

    # Card is generated from revision 1
    cards = client.get(f"/api/stories/{story_id}/cards").json()["cards"]
    card_id = cards[0]["id"]

    # Increment story revision by editing segment
    segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
    client.patch(
        f"/api/stories/{story_id}/segments/{segs[0]['id']}",
        json={"text": "Revision incrementing edit.", "expected_revision": 1},
    )

    # Check card is stale
    card_details = client.get(f"/api/cards/{card_id}").json()
    assert card_details["is_stale"] is True

    # Attempt to accept stale card
    accept_resp = client.patch(
        f"/api/cards/{card_id}",
        json={"review_state": "accepted"},
    )
    assert accept_resp.status_code == 409
    assert accept_resp.json()["error"]["code"] == "STALE_MEMORY_CARD"

    # Dismissing stale card is allowed
    dismiss_resp = client.patch(
        f"/api/cards/{card_id}",
        json={"review_state": "dismissed"},
    )
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["review_state"] == "dismissed"


# ==============================================================================
# 2. Archive Full-Text Search Tests
# ==============================================================================


def test_search_by_story_title():
    """Search matches story title."""
    story_id = "test-search-title-010"
    _create_test_story_fixture(None, story_id, title="Echoes of the Ancient Olive Grove")

    resp = client.get("/api/search?q=Ancient+Olive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    story_matches = [r for r in data["results"] if r["result_type"] == "story" and r["story_id"] == story_id]
    assert len(story_matches) == 1
    assert "Ancient Olive" in story_matches[0]["story_title"]


def test_search_by_speaker():
    """Search matches speaker label."""
    story_id = "test-search-speaker-011"
    _create_test_story_fixture(None, story_id, speaker="Bartholomew Montgomery")

    resp = client.get("/api/search?q=Bartholomew")
    assert resp.status_code == 200
    data = resp.json()
    matches = [r for r in data["results"] if r.get("speaker_label") == "Bartholomew Montgomery"]
    assert len(matches) >= 1


def test_search_inside_transcript_segments():
    """Search matches transcript segment text and provides audio seek metadata."""
    story_id = "test-search-transcript-012"
    _create_test_story_fixture(None, story_id)

    resp = client.get("/api/search?q=golden+marigolds")
    assert resp.status_code == 200
    data = resp.json()
    transcript_matches = [
        r for r in data["results"]
        if r["result_type"] == "transcript" and r["story_id"] == story_id
    ]
    assert len(transcript_matches) == 1
    match = transcript_matches[0]
    assert "golden marigolds" in match["text"].lower()
    assert match["start_ms"] == 1000
    assert match["end_ms"] == 5000
    assert "audio_url" in match


def test_search_memory_titles_and_summaries():
    """Search matches memory card title and summary."""
    story_id = "test-search-memory-013"
    _create_test_story_fixture(None, story_id)

    # Search title
    resp_title = client.get("/api/search?q=Marigold+Planting")
    assert resp_title.status_code == 200
    mem_matches = [
        r for r in resp_title.json()["results"]
        if r["result_type"] == "memory" and r["story_id"] == story_id
    ]
    assert len(mem_matches) >= 1
    assert mem_matches[0]["match_field"] == "title"

    # Search summary
    resp_summary = client.get("/api/search?q=grandmother")
    assert resp_summary.status_code == 200
    mem_summary_matches = [
        r for r in resp_summary.json()["results"]
        if r["result_type"] == "memory" and r["story_id"] == story_id
    ]
    assert len(mem_summary_matches) >= 1


def test_search_memory_themes():
    """Search matches themes stored in memory cards."""
    story_id = "test-search-themes-014"
    _create_test_story_fixture(None, story_id)

    resp = client.get("/api/search?q=heritage")
    assert resp.status_code == 200
    mem_matches = [
        r for r in resp.json()["results"]
        if r["result_type"] == "memory" and r["story_id"] == story_id
    ]
    assert len(mem_matches) >= 1
    assert "heritage" in mem_matches[0]["themes"]


def test_empty_and_whitespace_search_handling():
    """Empty or whitespace search query returns 422 INVALID_QUERY."""
    resp1 = client.get("/api/search?q=")
    assert resp1.status_code == 422
    resp2 = client.get("/api/search?q=   ")
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "INVALID_QUERY"


def test_search_no_results():
    """Search with non-existent query returns total 0 and empty list."""
    resp = client.get("/api/search?q=xylophone_nonexistent_term_98765")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert len(data["results"]) == 0


def test_search_unicode_and_punctuation():
    """Search handles Unicode, accents, and unusual punctuation safely."""
    story_id = "test-search-unicode-015"
    _create_test_story_fixture(None, story_id, title="L’histoire des fleurs d’automne & café")

    resp = client.get("/api/search?q=d’automne")
    assert resp.status_code == 200
    matches = [r for r in resp.json()["results"] if r["story_id"] == story_id]
    assert len(matches) >= 1


def test_search_query_length_and_result_limits():
    """Query length over 100 is rejected with 422, limit/offset pagination works."""
    long_query = "a" * 101
    resp = client.get(f"/api/search?q={long_query}")
    assert resp.status_code == 422

    # Pagination test
    resp_paged = client.get("/api/search?q=marigold&limit=1&offset=0")
    assert resp_paged.status_code == 200
    assert len(resp_paged.json()["results"]) <= 1


def test_search_sql_injection_safety():
    """Search handles SQL injection payloads safely without syntax error."""
    injection_queries = [
        "' OR 1=1 --",
        "'; DROP TABLE stories; --",
        "%_%",
        "\\",
    ]
    for q in injection_queries:
        resp = client.get("/api/search", params={"q": q})
        assert resp.status_code == 200
        assert isinstance(resp.json()["results"], list)


# ==============================================================================
# 3. Portable Story Export Tests
# ==============================================================================


def test_complete_valid_story_export_zip():
    """GET /api/stories/{id}/export generates a complete valid ZIP archive."""
    story_id = "test-export-valid-020"
    _create_test_story_fixture(None, story_id, title="Export Test Story")

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert f"echoarchive-{story_id}.zip" in resp.headers["content-disposition"]

    # Open ZIP in memory
    zip_bytes = resp.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        # Check ZIP Slip safety: no absolute paths or directory traversal
        for member in zf.namelist():
            assert not member.startswith("/")
            assert not member.startswith("\\")
            assert ".." not in member

        # Verify required members exist
        assert "audio.wav" in zf.namelist()
        assert "story.json" in zf.namelist()
        assert "transcript.json" in zf.namelist()
        assert "memories.json" in zf.namelist()
        assert "manifest.json" in zf.namelist()
        assert "story.html" in zf.namelist()

        # Check audio bytes match original
        original_audio = (MEDIA_DIR / f"{story_id}.wav").read_bytes()
        assert zf.read("audio.wav") == original_audio

        # Check manifest schema
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["format"] == "echoarchive-export-v1"
        assert manifest["story_id"] == story_id
        assert len(manifest["files"]) == 5  # audio, story, transcript, memories, story.html

        # Check story.json schema
        story_json = json.loads(zf.read("story.json").decode("utf-8"))
        assert story_json["id"] == story_id
        assert story_json["title"] == "Export Test Story"

        # Check transcript.json schema
        transcript_json = json.loads(zf.read("transcript.json").decode("utf-8"))
        assert transcript_json["segment_count"] == 2

        # Check memories.json schema
        memories_json = json.loads(zf.read("memories.json").decode("utf-8"))
        assert memories_json["card_count"] == 1
        assert memories_json["cards"][0]["model_provenance"] == "qwen2.5:1.5b"

        # Check story.html contents
        html_text = zf.read("story.html").decode("utf-8")
        assert "Export Test Story" in html_text
        assert "qwen2.5:1.5b" in html_text
        assert 'src="./audio.wav"' in html_text
        # Assert zero external CDNs or remote dependencies
        assert "http://" not in html_text
        assert "https://" not in html_text


def test_export_stale_memory_representation():
    """Export clearly labels stale memories in both memories.json and story.html."""
    story_id = "test-export-stale-021"
    _create_test_story_fixture(None, story_id, transcript_revision=1)

    # Increment story revision by editing segment
    segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
    client.patch(
        f"/api/stories/{story_id}/segments/{segs[0]['id']}",
        json={"text": "Edited text making card stale.", "expected_revision": 1},
    )

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 200

    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        memories_json = json.loads(zf.read("memories.json").decode("utf-8"))
        assert memories_json["cards"][0]["is_stale"] is True

        html_text = zf.read("story.html").decode("utf-8")
        assert "Stale (Transcript Modified)" in html_text


def test_export_active_job_conflict():
    """Export is rejected with 409 JOB_ACTIVE if a job is actively running."""
    story_id = "test-export-active-job-022"
    _create_test_story_fixture(None, story_id)

    # Insert an active running job into SQLite
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at)
            VALUES ('job-test-active-export', ?, 'extract', 'running', 'extracting', ?);
            """,
            (story_id, datetime.now(timezone.utc).isoformat()),
        )

    resp = client.get(f"/api/stories/{story_id}/export")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ACTIVE"


def test_export_missing_story_returns_404():
    """Export for non-existent story returns 404 STORY_NOT_FOUND."""
    resp = client.get("/api/stories/nonexistent-uuid-12345/export")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STORY_NOT_FOUND"


# ==============================================================================
# 4. Safe and Explicit Story Deletion Tests
# ==============================================================================


def test_delete_requires_explicit_confirmation():
    """DELETE /api/stories/{id} without confirm=true returns 422 CONFIRMATION_REQUIRED."""
    story_id = "test-delete-confirm-req-030"
    _create_test_story_fixture(None, story_id)

    # Without query or body confirm
    resp = client.delete(f"/api/stories/{story_id}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    # With confirm=false
    resp2 = client.delete(f"/api/stories/{story_id}?confirm=false")
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_successful_story_deletion():
    """DELETE /api/stories/{id}?confirm=true cascades removal of SQLite records and disk audio."""
    story_id = "test-delete-success-031"
    audio_path = _create_test_story_fixture(None, story_id)
    orig_transcript = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"

    assert audio_path.exists()
    assert orig_transcript.exists()

    resp = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert resp.json()["story_id"] == story_id

    # Verify audio file and transcript file deleted from disk
    assert not audio_path.exists()
    assert not orig_transcript.exists()

    # Verify SQLite cascade: story, segments, cards, sources no longer exist
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM stories WHERE id = ?", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0] == 0

    # Verify subsequent GET returns 404
    get_resp = client.get(f"/api/stories/{story_id}")
    assert get_resp.status_code == 404

    # Verify subsequent search does not find deleted story
    search_resp = client.get("/api/search?q=Courtyard+Marigolds")
    deleted_matches = [r for r in search_resp.json()["results"] if r.get("story_id") == story_id]
    assert len(deleted_matches) == 0


def test_delete_missing_story_returns_404():
    """DELETE on missing or already deleted story returns 404 STORY_NOT_FOUND."""
    resp = client.delete("/api/stories/already-deleted-uuid?confirm=true")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STORY_NOT_FOUND"


def test_delete_active_job_conflict():
    """DELETE rejects with 409 JOB_ACTIVE if an active job is queued or running."""
    story_id = "test-delete-active-job-032"
    _create_test_story_fixture(None, story_id)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, story_id, kind, status, stage, created_at)
            VALUES ('job-delete-conflict', ?, 'transcribe', 'running', 'transcribing', ?);
            """,
            (story_id, datetime.now(timezone.utc).isoformat()),
        )

    resp = client.delete(f"/api/stories/{story_id}?confirm=true")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_ACTIVE"


def test_delete_cross_story_isolation():
    """Deleting one story does not affect another story or its files."""
    story_a = "test-delete-iso-a-033"
    story_b = "test-delete-iso-b-034"
    audio_a = _create_test_story_fixture(None, story_a, title="Story Alpha")
    audio_b = _create_test_story_fixture(None, story_b, title="Story Beta")

    # Delete story A
    resp = client.delete(f"/api/stories/{story_a}?confirm=true")
    assert resp.status_code == 200

    # Story B must remain completely intact
    assert audio_b.exists()
    story_b_resp = client.get(f"/api/stories/{story_b}")
    assert story_b_resp.status_code == 200
    assert story_b_resp.json()["title"] == "Story Beta"
