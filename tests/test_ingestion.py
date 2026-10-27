"""Tests for audio ingestion API, streaming validation, consent enforcement, and media storage."""

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


def make_test_wav(duration_seconds: float = 3.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory valid PCM WAV audio bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_seconds * sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path: Path):
    """Ensure clean isolated data directories for each ingestion test."""
    test_db = tmp_path / "test_echoarchive.sqlite3"
    init_db(test_db)
    with patch("backend.main.get_db", lambda: get_db(test_db)), \
         patch("backend.jobs.get_db", lambda: get_db(test_db)):
        yield


def test_successful_valid_audio_upload():
    """Test successful story upload with explicit consent, producing durable SQLite record and private media file."""
    wav_bytes = make_test_wav(duration_seconds=3.0)
    response = client.post(
        "/api/stories",
        data={
            "title": "Summer by the Ocean",
            "speaker_label": "Arthur",
            "permission_confirmed": "true",
        },
        files={
            "audio": ("ocean_memory.wav", wav_bytes, "audio/wav"),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Summer by the Ocean"
    assert data["speaker_label"] == "Arthur"
    assert data["transcript_revision"] == 0
    assert data["audio_duration_ms"] >= 2900

    story_id = data["id"]

    # Verify retrieval from GET /api/stories/{id}
    detail_resp = client.get(f"/api/stories/{story_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["title"] == "Summer by the Ocean"
    assert detail["transcript_revision"] == 0

    # Verify media path was generated with server UUID, not original filename
    relpath = detail["audio_relpath"]
    assert "ocean_memory" not in relpath
    assert relpath.startswith("media/")
    assert relpath.endswith(".wav")


def test_missing_consent_rejected():
    """Test that missing or false permission_confirmed returns 422 CONSENT_REQUIRED."""
    wav_bytes = make_test_wav(duration_seconds=2.0)

    # Missing permission_confirmed
    resp1 = client.post(
        "/api/stories",
        data={"title": "No Consent Story"},
        files={"audio": ("sample.wav", wav_bytes, "audio/wav")},
    )
    assert resp1.status_code == 422
    data1 = resp1.json()
    assert data1["error"]["code"] == "CONSENT_REQUIRED"

    # permission_confirmed is false
    resp2 = client.post(
        "/api/stories",
        data={"title": "Denied Consent Story", "permission_confirmed": "false"},
        files={"audio": ("sample.wav", wav_bytes, "audio/wav")},
    )
    assert resp2.status_code == 422
    data2 = resp2.json()
    assert data2["error"]["code"] == "CONSENT_REQUIRED"


def test_unsupported_audio_extension_rejected():
    """Test that uploading unsupported extensions (.txt, .exe, .mkv) is rejected with 415."""
    resp = client.post(
        "/api/stories",
        data={"title": "Unsupported File", "permission_confirmed": "true"},
        files={"audio": ("recording.txt", b"Hello text", "text/plain")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


def test_spoofed_mime_type_with_corrupt_content():
    """Test that non-audio content labeled as audio/wav is detected and rejected with 415."""
    fake_audio = b"THIS IS NOT A VALID AUDIO STREAM HEADER"
    resp = client.post(
        "/api/stories",
        data={"title": "Spoofed MIME", "permission_confirmed": "true"},
        files={"audio": ("fake.wav", fake_audio, "audio/wav")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


def test_empty_audio_upload_rejected():
    """Test that an empty 0-byte upload is rejected with 415."""
    resp = client.post(
        "/api/stories",
        data={"title": "Empty File", "permission_confirmed": "true"},
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


def test_oversized_streaming_upload_rejected():
    """Test that uploads exceeding maximum byte limit are aborted during streaming with 413 AUDIO_TOO_LARGE."""
    wav_bytes = make_test_wav(duration_seconds=2.0)
    # Patch MAX_AUDIO_SIZE_BYTES to a small limit (512 bytes)
    with patch("backend.media.MAX_AUDIO_SIZE_BYTES", 512):
        resp = client.post(
            "/api/stories",
            data={"title": "Oversized Audio", "permission_confirmed": "true"},
            files={"audio": ("large.wav", wav_bytes, "audio/wav")},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "AUDIO_TOO_LARGE"


def test_audio_exceeding_duration_limit_rejected():
    """Test that audio exceeding 5 minutes (300 seconds) is rejected with 422 AUDIO_TOO_LONG."""
    wav_bytes = make_test_wav(duration_seconds=5.0)
    with patch("backend.media.MAX_AUDIO_DURATION_SECONDS", 3.0):
        resp = client.post(
            "/api/stories",
            data={"title": "Too Long Audio", "permission_confirmed": "true"},
            files={"audio": ("long.wav", wav_bytes, "audio/wav")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "AUDIO_TOO_LONG"


def test_path_traversal_filename_rejected():
    """Test that path traversal characters in filename are rejected with 422 PATH_TRAVERSAL."""
    wav_bytes = make_test_wav(duration_seconds=2.0)
    resp = client.post(
        "/api/stories",
        data={"title": "Traversal Attempt", "permission_confirmed": "true"},
        files={"audio": ("../../escape.wav", wav_bytes, "audio/wav")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"


def test_server_generated_unique_media_paths():
    """Test that repeated uploads generate distinct UUID filenames and never collide."""
    wav_bytes = make_test_wav(duration_seconds=1.0)
    resp1 = client.post(
        "/api/stories",
        data={"title": "Story 1", "permission_confirmed": "true"},
        files={"audio": ("test.wav", wav_bytes, "audio/wav")},
    )
    resp2 = client.post(
        "/api/stories",
        data={"title": "Story 2", "permission_confirmed": "true"},
        files={"audio": ("test.wav", wav_bytes, "audio/wav")},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201

    id1 = resp1.json()["id"]
    id2 = resp2.json()["id"]
    assert id1 != id2

    s1 = client.get(f"/api/stories/{id1}").json()
    s2 = client.get(f"/api/stories/{id2}").json()
    assert s1["audio_relpath"] != s2["audio_relpath"]


def test_list_stories_search_and_pagination():
    """Test GET /api/stories with query filtering and pagination."""
    wav_bytes = make_test_wav(duration_seconds=1.0)
    client.post(
        "/api/stories",
        data={"title": "A Story About Woodworking", "speaker_label": "Arthur", "permission_confirmed": "true"},
        files={"audio": ("wood.wav", wav_bytes, "audio/wav")},
    )
    client.post(
        "/api/stories",
        data={"title": "A Story About Marigolds", "speaker_label": "Clara", "permission_confirmed": "true"},
        files={"audio": ("flowers.wav", wav_bytes, "audio/wav")},
    )

    # Search for "Woodworking"
    resp = client.get("/api/stories?q=Woodworking")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["stories"][0]["title"] == "A Story About Woodworking"

    # Search for "Clara" (speaker_label)
    resp_speaker = client.get("/api/stories?q=Clara")
    assert resp_speaker.status_code == 200
    assert resp_speaker.json()["total"] == 1
    assert resp_speaker.json()["stories"][0]["speaker_label"] == "Clara"
