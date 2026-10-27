"""Evidence validation and citation grounding for EchoArchive Traceable Memories."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from backend.extraction import RawMemoryCard


class EvidenceValidationError(Exception):
    """Exception raised when memory evidence fails grounding or provenance checks."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class GroundedMemoryCard:
    """A validated memory card with verified supporting transcript text."""
    title: str
    summary: str
    themes: List[str]
    source_segment_ids: List[str]
    supporting_passages: List[str]  # Real transcript text from cited segments


def extract_quoted_phrases(text: str) -> List[str]:
    """Extract phrases enclosed in quotation marks from model summary."""
    # Matches "..." or “...” or ‘...’
    pattern = r'["“]([^"”]{4,})["”]|[\']([^\']{4,})[\']'
    matches = re.findall(pattern, text)
    quotes = []
    for m in matches:
        quote = m[0] or m[1]
        if quote and len(quote.strip()) > 3:
            quotes.append(quote.strip())
    return quotes


def normalize_for_quote_check(s: str) -> str:
    """Normalize text for robust word-sequence matching."""
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def validate_card_evidence(
    card: RawMemoryCard,
    valid_segment_dict: Dict[str, str],
    story_id: Optional[str] = None,
) -> GroundedMemoryCard:
    """
    Verify that:
    1. Card contains at least one source segment ID.
    2. Every cited source segment ID exists in the active story's transcript.
    3. Any claimed direct quotations in the summary or title actually appear in cited segments.
    4. Model summary is not treated as verbatim speech.
    Returns GroundedMemoryCard with genuine supporting passages from the transcript.
    """
    if not card.title or not (1 <= len(card.title.strip()) <= 160):
        raise EvidenceValidationError(
            "INVALID_AI_OUTPUT",
            "Memory card title must be between 1 and 160 characters."
        )

    if not card.summary or not (1 <= len(card.summary.strip()) <= 2000):
        raise EvidenceValidationError(
            "INVALID_AI_OUTPUT",
            "Memory card summary must be between 1 and 2000 characters."
        )

    if not card.source_segment_ids:
        raise EvidenceValidationError(
            "INVALID_EVIDENCE",
            f"Memory card '{card.title}' has no source segment references."
        )

    supporting_passages: List[str] = []
    combined_source_text = ""

    for seg_id in card.source_segment_ids:
        if seg_id not in valid_segment_dict:
            raise EvidenceValidationError(
                "INVALID_EVIDENCE",
                f"Memory card '{card.title}' cites nonexistent or cross-story segment ID '{seg_id}'."
            )
        passage = valid_segment_dict[seg_id]
        supporting_passages.append(passage)
        combined_source_text += " " + passage

    normalized_source = normalize_for_quote_check(combined_source_text)

    # Verify that alleged verbatim quotations exist in the source transcript
    all_quotes = extract_quoted_phrases(card.summary) + extract_quoted_phrases(card.title)
    for quote in all_quotes:
        normalized_quote = normalize_for_quote_check(quote)
        if not normalized_quote or normalized_quote not in normalized_source:
            raise EvidenceValidationError(
                "UNSUPPORTED_QUOTE",
                f"Card '{card.title}' includes alleged quotation '{quote}' which is not present in cited source segments."
            )

    return GroundedMemoryCard(
        title=card.title.strip(),
        summary=card.summary.strip(),
        themes=[str(t).strip() for t in card.themes if str(t).strip()],
        source_segment_ids=card.source_segment_ids,
        supporting_passages=supporting_passages,
    )


def validate_memory_cards_batch(
    cards: List[RawMemoryCard],
    valid_segment_dict: Dict[str, str],
    story_id: Optional[str] = None,
) -> List[GroundedMemoryCard]:
    """
    Validate a list of raw memory cards against a story's transcript segments.
    Rejects cards that cite invalid segments or contain unsupported quotations.
    """
    grounded_cards: List[GroundedMemoryCard] = []
    for card in cards:
        grounded = validate_card_evidence(card, valid_segment_dict, story_id)
        grounded_cards.append(grounded)
    return grounded_cards
