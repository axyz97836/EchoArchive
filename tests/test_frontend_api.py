"""Tests for Phase D frontend integration endpoints, review confirmation, and static serving."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.database import get_db, init_db
from backend.main import app


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "echoarchive_test.sqlite3"
        media_path = temp_path / "media"
        media_path.mkdir(parents=True, exist_ok=True)

        init_db(db_path)

        with (
            patch("backend.database.DATABASE_PATH", db_path),
            patch("backend.main.DATA_DIR", temp_path),
            patch("backend.main.MEDIA_DIR", media_path),
        ):
            yield {
                "db_path": db_path,
                "media_path": media_path,
                "temp_path": temp_path,
            }


def test_story_review_confirmation_lifecycle(test_env):
    """Test explicit human transcript review confirmation endpoint."""
    client = TestClient(app)
    db_path = test_env["db_path"]

    story_id = "story-review-test"
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, speaker_label, consent_confirmed_at, audio_relpath,
                audio_media_type, audio_size_bytes, audio_duration_ms,
                transcript_revision, transcript_reviewed_at, created_at, updated_at
            ) VALUES (?, 'Review Test Story', 'Grandpa', '2026-10-28T00:00:00Z',
                     'media/test.wav', 'audio/wav', 1024, 5000, 1, NULL,
                     '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """,
            (story_id,),
        )

    # 1. Attempt review without transcript segments -> 422 NO_TRANSCRIPT
    resp = client.post(f"/api/stories/{story_id}/review")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_TRANSCRIPT"

    # 2. Add transcript segment
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO transcript_segments (
                id, story_id, segment_index, start_ms, end_ms, text, user_edited
            ) VALUES ('seg-1', ?, 0, 0, 3000, 'We used to gather on the porch.', 0);
            """,
            (story_id,),
        )

    # 3. Confirm human review -> 200 OK
    resp = client.post(f"/api/stories/{story_id}/review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_reviewed"] is True
    assert data["transcript_reviewed_at"] is not None

    # 4. Verify in story get
    get_resp = client.get(f"/api/stories/{story_id}")
    assert get_resp.status_code == 200
    story_data = get_resp.json()
    assert story_data["is_reviewed"] is True
    assert story_data["transcript_segments_count"] == 1
    assert story_data["memory_cards_count"] == 0

    # 5. Non-existent story review -> 404
    bad_resp = client.post("/api/stories/nonexistent-id/review")
    assert bad_resp.status_code == 404


def test_story_list_metadata_fields(test_env):
    """Test list_stories returns memory counts, segment counts, and review flags."""
    client = TestClient(app)
    db_path = test_env["db_path"]

    story_id = "story-meta-test"
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, speaker_label, consent_confirmed_at, audio_relpath,
                audio_media_type, audio_size_bytes, audio_duration_ms,
                transcript_revision, transcript_reviewed_at, created_at, updated_at
            ) VALUES (?, 'Metadata Story', 'Elder', '2026-10-28T00:00:00Z',
                     'media/meta.wav', 'audio/wav', 2048, 8000, 1, '2026-10-28T01:00:00Z',
                     '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """,
            (story_id,),
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (
                id, story_id, segment_index, start_ms, end_ms, text, user_edited
            ) VALUES ('seg-meta-1', ?, 0, 0, 4000, 'Memories are precious.', 0);
            """,
            (story_id,),
        )
        conn.execute(
            """
            INSERT INTO memory_cards (
                id, story_id, title, summary, themes_json,
                generated_from_revision, review_state, model_provenance, created_at
            ) VALUES ('card-meta-1', ?, 'Cherished Days', 'A remembrance of old times.', '["family"]',
                     1, 'draft', 'qwen2.5:1.5b', '2026-10-28T02:00:00Z');
            """,
            (story_id,),
        )

    list_resp = client.get("/api/stories")
    assert list_resp.status_code == 200
    stories = list_resp.json()["stories"]
    target = next((s for s in stories if s["id"] == story_id), None)
    assert target is not None
    assert target["is_reviewed"] is True
    assert target["memory_cards_count"] == 1
    assert target["transcript_segments_count"] == 1


def test_frontend_index_and_static_assets_serving():
    """Test that / and /app serve index.html and static assets are delivered."""
    client = TestClient(app)

    # 1. Root route
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert "text/html" in root_resp.headers["content-type"]
    assert "EchoArchive" in root_resp.text
    assert "The Archive After Dark" in root_resp.text or "Traceable Memories" in root_resp.text

    # 2. App route
    app_resp = client.get("/app")
    assert app_resp.status_code == 200
    assert "text/html" in app_resp.headers["content-type"]

    # 3. CSS delivery
    css_resp = client.get("/static/css/style.css")
    assert css_resp.status_code == 200
    assert "text/css" in css_resp.headers["content-type"]
    assert "--color-midnight: #1B252B" in css_resp.text

    # 4. JS delivery
    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "javascript" in js_resp.headers["content-type"]
    assert "EchoArchive" in js_resp.text

