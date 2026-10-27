"""Tests for FastAPI backend loopback API endpoints."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_api_health_endpoint():
    """Test the /api/health endpoint structure and truthful reporting."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] in ("ready", "degraded")
    assert "services" in data

    services = data["services"]
    assert "speech_recognition" in services
    assert "media_preprocessing" in services
    assert "language_model" in services
    assert "database" in services
    assert "storage" in services

    # Ensure engine names are reported accurately
    assert services["speech_recognition"]["engine"] == "whisper.cpp"
    assert services["media_preprocessing"]["tool"] == "ffmpeg"
    assert services["language_model"]["provider"] == "ollama"
    assert services["database"]["engine"] == "sqlite3"
    assert services["storage"]["local_only"] is True
