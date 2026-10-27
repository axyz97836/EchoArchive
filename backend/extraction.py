"""Ollama extraction adapter for local Qwen2.5 memory card generation."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import httpx

from backend.config import (
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT_SECONDS,
    QWEN_MODEL_NAME,
)


class ExtractionError(Exception):
    """Exception raised when memory extraction fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RawMemoryCard:
    """Represents an extracted memory card before database persistence."""
    title: str
    summary: str
    themes: List[str]
    source_segment_ids: List[str]


EXTRACTION_SYSTEM_PROMPT = """You are an evidence-grounded memory indexing assistant for personal spoken audio archives.
Your role is to organize authentic spoken memories into concise memory cards.

CRITICAL RULES:
1. Every card MUST have a 'source_segment_ids' array containing one or more segment IDs from the input (e.g. ["seg-000", "seg-001"]).
2. Ground all summaries strictly in what the speaker actually said.
3. NEVER invent people, dates, places, family relationships, or biographical facts not stated in the transcript.
4. Do NOT present summaries as verbatim quotations.
5. If there are no meaningful memories, return {"cards": []}.

Output MUST be valid JSON adhering to this exact schema:
{
  "cards": [
    {
      "title": "Concise descriptive title (1 to 160 chars)",
      "summary": "Clear summary grounded only in cited segments (1 to 2000 chars)",
      "themes": ["theme1", "theme2"],
      "source_segment_ids": ["seg-000"]
    }
  ]
}"""


def check_ollama_available(base_url: Optional[str] = None) -> bool:
    """Check if the local Ollama API server is running and reachable."""
    url = f"{base_url or OLLAMA_BASE_URL}/api/tags"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url)
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        return False


def check_qwen_model_available(model_name: Optional[str] = None, base_url: Optional[str] = None) -> bool:
    """Check if the specified Qwen model is downloaded in Ollama."""
    target_model = model_name or QWEN_MODEL_NAME
    url = f"{base_url or OLLAMA_BASE_URL}/api/tags"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(target_model in m for m in models)
    except Exception:
        return False


def extract_memories_from_segments(
    segments: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[int] = None,
) -> List[RawMemoryCard]:
    """
    Send formatted transcript segments to local Ollama /api/chat with Qwen2.5.
    Returns parsed and schema-validated RawMemoryCard objects.
    """
    if not segments:
        return []

    target_model = model_name or QWEN_MODEL_NAME
    api_url = f"{base_url or OLLAMA_BASE_URL}/api/chat"
    req_timeout = timeout or OLLAMA_TIMEOUT_SECONDS

    # Format transcript segments for prompt
    transcript_lines = []
    for seg in segments:
        seg_id = seg.get("id") or f"seg-{seg.get('segment_index', 0):03d}"
        text = seg.get("text", "").strip()
        transcript_lines.append(f"[{seg_id}] {text}")

    user_content = (
        "Transcript Segments:\n"
        + "\n".join(transcript_lines)
        + "\n\nExtract grounded memory cards in JSON. Remember to include 'source_segment_ids' referencing the segment IDs above (e.g. [\"seg-000\"])."
    )

    payload = {
        "model": target_model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "options": {
            "temperature": 0.1,  # low temperature for factual grounding
        },
    }

    try:
        with httpx.Client(timeout=float(req_timeout)) as client:
            resp = client.post(api_url, json=payload)
    except httpx.ConnectError:
        raise ExtractionError(
            "OLLAMA_UNAVAILABLE",
            "Ollama server is not running on localhost (127.0.0.1:11434). Please start Ollama."
        )
    except httpx.TimeoutException:
        raise ExtractionError(
            "OLLAMA_TIMEOUT",
            f"Ollama request timed out after {req_timeout}s."
        )
    except Exception as e:
        raise ExtractionError("OLLAMA_UNAVAILABLE", f"Failed to connect to Ollama: {str(e)}")

    if resp.status_code != 200:
        raise ExtractionError(
            "OLLAMA_FAILED",
            f"Ollama returned HTTP status {resp.status_code}: {resp.text[:200]}"
        )

    try:
        result = resp.json()
        message_content = result.get("message", {}).get("content", "")
        parsed = json.loads(message_content)
    except (json.JSONDecodeError, AttributeError) as err:
        raise ExtractionError(
            "INVALID_AI_OUTPUT",
            f"Ollama returned invalid or malformed JSON content: {str(err)}"
        )

    if not isinstance(parsed, dict) or "cards" not in parsed:
        raise ExtractionError(
            "INVALID_AI_OUTPUT",
            "Output JSON must contain top-level 'cards' array."
        )

    cards_data = parsed["cards"]
    if not isinstance(cards_data, list):
        raise ExtractionError("INVALID_AI_OUTPUT", "'cards' field must be an array.")

    validated_cards: List[RawMemoryCard] = []
    for idx, card in enumerate(cards_data):
        if not isinstance(card, dict):
            raise ExtractionError("INVALID_AI_OUTPUT", f"Card at index {idx} is not an object.")

        title = card.get("title")
        summary = card.get("summary")
        themes = card.get("themes", [])

        # Check source segment ID candidates
        raw_source_ids = (
            card.get("source_segment_ids")
            or card.get("source_ids")
            or card.get("segments")
            or card.get("source_segments")
        )

        # Validate title
        if not isinstance(title, str) or not (1 <= len(title.strip()) <= 160):
            raise ExtractionError(
                "INVALID_AI_OUTPUT",
                f"Card {idx} title must be a string between 1 and 160 characters."
            )

        # Validate summary
        if not isinstance(summary, str) or not (1 <= len(summary.strip()) <= 2000):
            raise ExtractionError(
                "INVALID_AI_OUTPUT",
                f"Card {idx} summary must be a string between 1 and 2000 characters."
            )

        # Validate themes
        if not isinstance(themes, list) or not all(isinstance(t, (str, int)) for t in themes):
            raise ExtractionError(
                "INVALID_AI_OUTPUT",
                f"Card {idx} themes must be an array."
            )

        # Normalize source segment IDs
        normalized_ids: List[str] = []
        if isinstance(raw_source_ids, list):
            for item in raw_source_ids:
                if isinstance(item, int):
                    normalized_ids.append(f"seg-{item:03d}")
                elif isinstance(item, str) and item.strip():
                    cleaned = item.strip().strip("[]'\"")
                    if cleaned:
                        normalized_ids.append(cleaned)

        if not normalized_ids:
            raise ExtractionError(
                "INVALID_EVIDENCE",
                f"Card {idx} ('{title}') must have at least one valid source segment ID."
            )

        validated_cards.append(
            RawMemoryCard(
                title=title.strip(),
                summary=summary.strip(),
                themes=[str(t).strip() for t in themes if str(t).strip()],
                source_segment_ids=normalized_ids,
            )
        )

    return validated_cards
