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


def validate_card_evidence(
    card: RawMemoryCard,
    valid_segment_dict: Dict[str, str],
    story_id: Optional[str] = None,
) -> GroundedMemoryCard:
    """
    Verify that:
    1. Card contains at least one source segment ID.
    2. Every cited source segment ID exists in the active story's transcript.
    3. Any claimed direct quotations in the summary actually appear in cited segments.
    4. Model summary is not treated as verbatim speech.
    Returns GroundedMemoryCard with genuine supporting passages from the transcript.
    """
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
        combined_source_text += " " + passage.lower()

    # Verify that alleged verbatim quotations exist in the source transcript
    quotes = extract_quoted_phrases(card.summary)
    for quote in quotes:
        normalized_quote = quote.lower()
        if normalized_quote not in combined_source_text:
            raise EvidenceValidationError(
                "UNSUPPORTED_QUOTE",
                f"Card '{card.title}' includes alleged quotation '{quote}' which is not present in cited source segments."
            )

    return GroundedMemoryCard(
        title=card.title,
        summary=card.summary,
        themes=card.themes,
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
