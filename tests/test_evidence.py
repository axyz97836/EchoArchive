"""Deterministic unit tests for evidence validation and citation grounding."""

import pytest

from backend.evidence import (
    EvidenceValidationError,
    validate_card_evidence,
    validate_memory_cards_batch,
)
from backend.extraction import RawMemoryCard

VALID_STORY_SEGMENTS = {
    "seg-001": "My grandmother taught me how to save seeds from the sweetest heirloom tomatoes.",
    "seg-002": "Every August we laid them out on parchment paper in the sunny kitchen window.",
    "seg-003": "She said the red ones always had the most flavor.",
}


def test_valid_evidence_citations():
    """Test that cards citing genuine existing segments succeed and retain supporting passages."""
    card = RawMemoryCard(
        title="Saving Tomato Seeds",
        summary="The speaker learned seed-saving traditions from their grandmother.",
        themes=["gardening", "family"],
        source_segment_ids=["seg-001", "seg-002"],
    )

    grounded = validate_card_evidence(card, VALID_STORY_SEGMENTS)
    assert grounded.title == "Saving Tomato Seeds"
    assert len(grounded.supporting_passages) == 2
    assert "heirloom tomatoes" in grounded.supporting_passages[0]
    assert "parchment paper" in grounded.supporting_passages[1]


def test_nonexistent_segment_citation_rejected():
    """Test that a card citing a nonexistent segment ID is rejected with INVALID_EVIDENCE."""
    card = RawMemoryCard(
        title="Fictional Recipe",
        summary="Grandmother made tomato soup.",
        themes=["cooking"],
        source_segment_ids=["seg-999"],  # Nonexistent segment
    )

    with pytest.raises(EvidenceValidationError) as exc:
        validate_card_evidence(card, VALID_STORY_SEGMENTS)
    assert exc.value.code == "INVALID_EVIDENCE"
    assert "nonexistent or cross-story segment" in exc.value.message


def test_empty_citations_rejected():
    """Test that a card with empty source segment IDs is rejected with INVALID_EVIDENCE."""
    card = RawMemoryCard(
        title="Seed Traditions",
        summary="Memories of seeds.",
        themes=["gardening"],
        source_segment_ids=[],
    )

    with pytest.raises(EvidenceValidationError) as exc:
        validate_card_evidence(card, VALID_STORY_SEGMENTS)
    assert exc.value.code == "INVALID_EVIDENCE"
    assert "no source segment references" in exc.value.message


def test_unsupported_quotation_rejected():
    """Test that a card with an invented verbatim quotation not present in transcript is rejected."""
    card = RawMemoryCard(
        title="Grandmother's Advice",
        # Fabricated quote inside quotes:
        summary='She told me "Always water the tomatoes before sunrise, or they will surely wither and die."',
        themes=["advice"],
        source_segment_ids=["seg-001"],
    )

    with pytest.raises(EvidenceValidationError) as exc:
        validate_card_evidence(card, VALID_STORY_SEGMENTS)
    assert exc.value.code == "UNSUPPORTED_QUOTE"
    assert "which is not present in cited source segments" in exc.value.message


def test_supported_quotation_accepted():
    """Test that a card whose quoted phrase actually appears in the transcript passes validation."""
    card = RawMemoryCard(
        title="Grandmother's Tomato Flavor",
        summary='She noted that "the red ones always had the most flavor" when drying seeds.',
        themes=["cooking", "flavor"],
        source_segment_ids=["seg-003"],
    )

    grounded = validate_card_evidence(card, VALID_STORY_SEGMENTS)
    assert grounded.title == "Grandmother's Tomato Flavor"
    assert len(grounded.supporting_passages) == 1
    assert "most flavor" in grounded.supporting_passages[0]


def test_batch_validation_rejects_on_any_invalid():
    """Test that batch validation fails if any card contains invalid evidence."""
    cards = [
        RawMemoryCard(
            title="Good Card",
            summary="A genuine memory.",
            themes=["seeds"],
            source_segment_ids=["seg-001"],
        ),
        RawMemoryCard(
            title="Bad Card",
            summary="An ungrounded memory.",
            themes=["unknown"],
            source_segment_ids=["seg-404"],
        ),
    ]

    with pytest.raises(EvidenceValidationError) as exc:
        validate_memory_cards_batch(cards, VALID_STORY_SEGMENTS)
    assert exc.value.code == "INVALID_EVIDENCE"
