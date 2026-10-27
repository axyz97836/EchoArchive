"""Deterministic unit tests for Ollama Qwen extraction adapter."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.extraction import (
    ExtractionError,
    RawMemoryCard,
    extract_memories_from_segments,
)

SAMPLE_SEGMENTS = [
    {"id": "seg-000", "segment_index": 0, "text": "We planted apple trees in the garden behind our old barn."},
    {"id": "seg-001", "segment_index": 1, "text": "Every October we pressed cider with our neighbors."},
]


def test_ollama_unavailable_raises_error():
    """Test that connection failure to Ollama raises OLLAMA_UNAVAILABLE."""
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "OLLAMA_UNAVAILABLE"


def test_ollama_timeout_raises_error():
    """Test that timeout talking to Ollama raises OLLAMA_TIMEOUT."""
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Timed out")):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS, timeout=5)
        assert exc.value.code == "OLLAMA_TIMEOUT"


def test_ollama_http_failure():
    """Test that non-200 HTTP response raises OLLAMA_FAILED."""
    mock_resp = MagicMock(status_code=500, text="Internal server error")
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "OLLAMA_FAILED"


def test_malformed_qwen_json():
    """Test that malformed JSON returned in Ollama message raises INVALID_AI_OUTPUT."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "message": {"content": "This is raw text, not valid JSON!"}
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "INVALID_AI_OUTPUT"


def test_missing_cards_array():
    """Test that JSON output without 'cards' array raises INVALID_AI_OUTPUT."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "message": {"content": json.dumps({"summary": "A story about cider."})}
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "INVALID_AI_OUTPUT"


def test_missing_title_in_card():
    """Test that a card missing a title raises INVALID_AI_OUTPUT."""
    mock_resp = MagicMock(status_code=200)
    card_data = {
        "cards": [
            {
                "summary": "Pressing cider in October.",
                "themes": ["tradition"],
                "source_segment_ids": ["seg-001"],
            }
        ]
    }
    mock_resp.json.return_value = {"message": {"content": json.dumps(card_data)}}
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "INVALID_AI_OUTPUT"


def test_title_too_long():
    """Test that a card with title > 160 chars raises INVALID_AI_OUTPUT."""
    mock_resp = MagicMock(status_code=200)
    card_data = {
        "cards": [
            {
                "title": "A" * 165,
                "summary": "Pressing cider in October.",
                "themes": ["tradition"],
                "source_segment_ids": ["seg-001"],
            }
        ]
    }
    mock_resp.json.return_value = {"message": {"content": json.dumps(card_data)}}
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "INVALID_AI_OUTPUT"


def test_missing_source_segment_ids():
    """Test that a card with missing or empty source IDs raises INVALID_EVIDENCE."""
    mock_resp = MagicMock(status_code=200)
    card_data = {
        "cards": [
            {
                "title": "Autumn Cider",
                "summary": "Pressing cider with neighbors.",
                "themes": ["tradition"],
                "source_segment_ids": [],  # empty citations!
            }
        ]
    }
    mock_resp.json.return_value = {"message": {"content": json.dumps(card_data)}}
    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc:
            extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert exc.value.code == "INVALID_EVIDENCE"


def test_valid_qwen_extraction():
    """Test that well-formed Qwen JSON output is properly parsed into RawMemoryCard objects."""
    mock_resp = MagicMock(status_code=200)
    card_data = {
        "cards": [
            {
                "title": "Planting Apple Trees and Pressing Cider",
                "summary": "The speaker remembers planting apple trees and gathering with neighbors each October.",
                "themes": ["gardening", "community tradition"],
                "source_segment_ids": ["seg-000", "seg-001"],
            }
        ]
    }
    mock_resp.json.return_value = {"message": {"content": json.dumps(card_data)}}
    with patch("httpx.Client.post", return_value=mock_resp):
        cards = extract_memories_from_segments(SAMPLE_SEGMENTS)
        assert len(cards) == 1
        assert cards[0].title == "Planting Apple Trees and Pressing Cider"
        assert len(cards[0].source_segment_ids) == 2
        assert "seg-000" in cards[0].source_segment_ids
        assert "seg-001" in cards[0].source_segment_ids
