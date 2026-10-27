"""Deterministic unit and integration tests for transcript review and human correction API."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import ORIGINAL_TRANSCRIPTS_DIR
from backend.database import get_db, init_db
from backend.main import app

client = TestClient(app)


@pytest.fixture
def story_with_transcript(tmp_path: Path):
    """Seed a test database with a story and two initial machine-transcribed segments."""
    test_db = tmp_path / "test_corrections.sqlite3"
    init_db(test_db)

    orig_dir = tmp_path / "original_transcripts"
    orig_dir.mkdir(parents=True, exist_ok=True)

    story_id = "story-maine-1"
    seg1_id = "seg-part-0"
    seg2_id = "seg-part-1"

    now_iso = "2026-10-28T00:00:00Z"

    with get_db(test_db) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, consent_confirmed_at, audio_relpath, audio_media_type,
                audio_size_bytes, audio_duration_ms, transcript_revision, created_at, updated_at
            ) VALUES (?, 'Sailing Story', ?, 'media/sailing.wav', 'audio/wav', 50000, 18000, 1, ?, ?);
            """,
            (story_id, now_iso, now_iso, now_iso)
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 0, 0, 5240, 'When I was seven years old, my grandfather Arthur built a sailboat', 0);
            """,
            (seg1_id, story_id)
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text, user_edited)
            VALUES (?, ?, 1, 5240, 6680, 'in Coastal Main.', 0);
            """,
            (seg2_id, story_id)
        )

    # Save original immutable transcript JSON
    orig_json_path = orig_dir / f"{story_id}.json"
    with open(orig_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "story_id": story_id,
                "transcribed_at": now_iso,
                "segments": [
                    {"segment_index": 0, "text": "When I was seven years old, my grandfather Arthur built a sailboat"},
                    {"segment_index": 1, "text": "in Coastal Main."},
                ]
            },
            f
        )

    with patch("backend.main.get_db", lambda: get_db(test_db)):
        yield {
            "db_file": test_db,
            "story_id": story_id,
            "seg1_id": seg1_id,
            "seg2_id": seg2_id,
            "orig_json_path": orig_json_path,
        }


def test_transcript_segments_retrieval_order(story_with_transcript):
    """Test GET /api/stories/{id}/segments returns chronological segments and current revision."""
    story_id = story_with_transcript["story_id"]
    resp = client.get(f"/api/stories/{story_id}/segments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["story_id"] == story_id
    assert data["transcript_revision"] == 1
    segments = data["segments"]
    assert len(segments) == 2
    assert segments[0]["segment_index"] == 0
    assert segments[1]["segment_index"] == 1
    assert segments[1]["text"] == "in Coastal Main."
    assert segments[1]["user_edited"] == 0


def test_successful_transcript_correction(story_with_transcript):
    """
    Test human correction of actual observed Phase A error:
    'in Coastal Main.' -> 'in coastal Maine.'
    Revision increments to 2, user_edited becomes 1.
    """
    story_id = story_with_transcript["story_id"]
    seg2_id = story_with_transcript["seg2_id"]

    resp = client.patch(
        f"/api/stories/{story_id}/segments/{seg2_id}",
        json={"text": "in coastal Maine.", "expected_revision": 1},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["transcript_revision"] == 2
    assert data["segment"]["text"] == "in coastal Maine."
    assert data["segment"]["user_edited"] == 1

    # Verify updated revision on story
    story_resp = client.get(f"/api/stories/{story_id}")
    assert story_resp.json()["transcript_revision"] == 2

    # Verify original machine transcript file remains unchanged
    with open(story_with_transcript["orig_json_path"], "r") as f:
        orig_data = json.load(f)
    assert orig_data["segments"][1]["text"] == "in Coastal Main."


def test_stale_expected_revision_conflict(story_with_transcript):
    """Test that submitting an edit with a stale expected_revision returns 409 REVISION_CONFLICT."""
    story_id = story_with_transcript["story_id"]
    seg2_id = story_with_transcript["seg2_id"]

    # First edit succeeds (1 -> 2)
    resp1 = client.patch(
        f"/api/stories/{story_id}/segments/{seg2_id}",
        json={"text": "in coastal Maine.", "expected_revision": 1},
    )
    assert resp1.status_code == 200
    assert resp1.json()["transcript_revision"] == 2

    # Attempt second edit with stale expected_revision=1
    resp2 = client.patch(
        f"/api/stories/{story_id}/segments/{seg2_id}",
        json={"text": "in Coastal Maine!", "expected_revision": 1},
    )
    assert resp2.status_code == 409
    error = resp2.json()["error"]
    assert error["code"] == "REVISION_CONFLICT"
    assert "Expected 1, but current revision is 2" in error["message"]


def test_cross_story_segment_edit_rejected(story_with_transcript):
    """Test that attempting to edit a segment belonging to another story is rejected with 404."""
    seg2_id = story_with_transcript["seg2_id"]
    other_story_id = "different-story-uuid-999"

    resp = client.patch(
        f"/api/stories/{other_story_id}/segments/{seg2_id}",
        json={"text": "in coastal Maine.", "expected_revision": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STORY_NOT_FOUND"


def test_empty_or_whitespace_correction_rejected(story_with_transcript):
    """Test that empty or whitespace-only corrections are rejected with 422."""
    story_id = story_with_transcript["story_id"]
    seg2_id = story_with_transcript["seg2_id"]

    resp = client.patch(
        f"/api/stories/{story_id}/segments/{seg2_id}",
        json={"text": "   ", "expected_revision": 1},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_CORRECTION"


def test_concurrent_corrections_optimistic_concurrency(story_with_transcript):
    """Test that when two callers attempt corrections from the same revision, only one succeeds and the other gets 409."""
    import concurrent.futures

    story_id = story_with_transcript["story_id"]
    seg2_id = story_with_transcript["seg2_id"]

    def submit_edit(text: str):
        return client.patch(
            f"/api/stories/{story_id}/segments/{seg2_id}",
            json={"text": text, "expected_revision": 1},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(submit_edit, "first correction")
        f2 = executor.submit(submit_edit, "second correction")
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409], f"Expected exactly one 200 and one 409, got {statuses}"
