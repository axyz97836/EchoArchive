"""Deterministic tests for audio byte-range streaming, origin/host security, and error hygiene."""

import io
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.config import DATA_DIR, MEDIA_DIR
from backend.database import get_db, init_db
from backend.main import app

client = TestClient(app)


@pytest.fixture
def story_with_audio(tmp_path: Path):
    """Seed test database and audio media file."""
    test_db = tmp_path / "test_sec.sqlite3"
    init_db(test_db)

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    story_id = "story-audio-sec-1"
    audio_path = media_dir / f"{story_id}.wav"

    # Write a valid 1000-byte dummy audio content
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 500)
    audio_bytes = buf.getvalue()
    audio_path.write_bytes(audio_bytes)

    with get_db(test_db) as conn:
        conn.execute(
            """
            INSERT INTO stories (
                id, title, consent_confirmed_at, audio_relpath, audio_media_type,
                audio_size_bytes, audio_duration_ms, transcript_revision, created_at, updated_at
            ) VALUES (?, 'Audio Security Test', '2026-10-28T00:00:00Z', ?, 'audio/wav', ?, 1000, 0, '2026-10-28T00:00:00Z', '2026-10-28T00:00:00Z');
            """,
            (story_id, f"media/{story_id}.wav", len(audio_bytes))
        )

    with patch("backend.main.get_db", lambda: get_db(test_db)), \
         patch("backend.main.DATA_DIR", tmp_path), \
         patch("backend.main.MEDIA_DIR", media_dir):
        yield {
            "story_id": story_id,
            "audio_path": audio_path,
            "total_bytes": len(audio_bytes),
        }


def test_full_audio_retrieval(story_with_audio):
    """Test standard GET /api/stories/{id}/audio returns 200 with Accept-Ranges."""
    story_id = story_with_audio["story_id"]
    resp = client.get(f"/api/stories/{story_id}/audio")
    assert resp.status_code == 200
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Type") == "audio/wav"
    assert len(resp.content) == story_with_audio["total_bytes"]


def test_audio_byte_range_streaming(story_with_audio):
    """Test seekable audio playback via HTTP Range header returns 206 Partial Content."""
    story_id = story_with_audio["story_id"]
    total = story_with_audio["total_bytes"]

    # Request first 100 bytes (0-99)
    resp = client.get(
        f"/api/stories/{story_id}/audio",
        headers={"Range": "bytes=0-99"},
    )
    assert resp.status_code == 206
    assert resp.headers.get("Content-Range") == f"bytes 0-99/{total}"
    assert resp.headers.get("Content-Length") == "100"
    assert len(resp.content) == 100

    # Request tail bytes
    resp_tail = client.get(
        f"/api/stories/{story_id}/audio",
        headers={"Range": "bytes=100-199"},
    )
    assert resp_tail.status_code == 206
    assert resp_tail.headers.get("Content-Range") == f"bytes 100-199/{total}"
    assert len(resp_tail.content) == 100


def test_invalid_byte_range_returns_416(story_with_audio):
    """Test out-of-range byte requests return 416 Range Not Satisfiable."""
    story_id = story_with_audio["story_id"]
    total = story_with_audio["total_bytes"]

    resp = client.get(
        f"/api/stories/{story_id}/audio",
        headers={"Range": f"bytes={total + 500}-{total + 1000}"},
    )
    assert resp.status_code == 416
    assert resp.headers.get("Content-Range") == f"bytes */{total}"


def test_untrusted_origin_rejected(story_with_audio):
    """Test that state-changing requests from untrusted origins are blocked with 403."""
    story_id = story_with_audio["story_id"]

    # Attempt POST with malicious external Origin
    resp = client.post(
        f"/api/stories/{story_id}/transcribe",
        headers={"Origin": "https://malicious-website.com"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "FORBIDDEN"
    assert "Cross-origin" in data["error"]["message"]


def test_trusted_loopback_origin_accepted(story_with_audio):
    """Test that requests from 127.0.0.1 or localhost origins are accepted."""
    story_id = story_with_audio["story_id"]

    with patch("backend.main.global_worker.enqueue_transcription") as mock_enqueue:
        mock_enqueue.return_value = {
            "job_id": "job-1",
            "story_id": story_id,
            "kind": "transcribe",
            "status": "queued",
            "stage": "queued",
        }
        resp = client.post(
            f"/api/stories/{story_id}/transcribe",
            headers={"Origin": "http://127.0.0.1:8766"},
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"


def test_untrusted_host_header_rejected(story_with_audio):
    """Test that requests with untrusted Host header are rejected with 403."""
    story_id = story_with_audio["story_id"]

    resp = client.post(
        f"/api/stories/{story_id}/transcribe",
        headers={"Host": "evil.attacker.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_error_response_hygiene(story_with_audio):
    """Verify that error responses do not leak server paths or python stack traces."""
    # Test non-existent story error
    resp = client.get("/api/stories/nonexistent-id-000")
    assert resp.status_code == 404
    body_text = resp.text
    assert "/Users/" not in body_text
    assert "Traceback" not in body_text
    assert "echoarchive.sqlite3" not in body_text
    data = resp.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
