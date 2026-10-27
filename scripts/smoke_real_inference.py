#!/usr/bin/env python3
"""
EchoArchive — Reproducible Real Local AI Smoke Demonstration

Demonstrates the offline AI pipeline:
Synthetic Audio (Fictional Story)
  → Real whisper.cpp Transcription (Metal GPU accelerated)
  → Timestamped Segments
  → Real Local Qwen Extraction (Ollama qwen2.5:1.5b)
  → Validated Memory Cards
  → Verified Source References & Anti-Hallucination Rejection
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import TMP_DIR
from backend.evidence import (
    EvidenceValidationError,
    validate_card_evidence,
    validate_memory_cards_batch,
)
from backend.extraction import (
    RawMemoryCard,
    extract_memories_from_segments,
)
from backend.media import normalize_to_whisper_wav, validate_audio
from backend.transcription import transcribe_audio_file

# Strictly fictional story — zero private or personal recollections
FICTIONAL_STORY = (
    "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop in coastal Maine. "
    "Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. "
    "He always told me that patience is like trimming the sail: you cannot control the wind, but you can always guide your boat."
)


def generate_synthetic_audio(output_wav: Path) -> None:
    """Generate a clean synthetic audio file using macOS speech synthesis and FFmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
        aiff_path = Path(tmp_aiff.name)

    try:
        # Use macOS speech synthesis (consenting synthetic voice)
        subprocess.run(
            ["say", "-v", "Samantha", "-o", str(aiff_path), FICTIONAL_STORY],
            check=True,
            capture_output=True,
        )
        # Convert to 16kHz mono WAV for whisper.cpp
        normalize_to_whisper_wav(aiff_path, output_wav)
    finally:
        if aiff_path.exists():
            aiff_path.unlink()


def main() -> int:
    print("=" * 65)
    print(" EchoArchive — Real Local AI Proof of Concept (Phase A)")
    print("=" * 65)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    synthetic_wav = TMP_DIR / "synthetic_fictional_test.wav"

    try:
        # Step 1: Generate synthetic fictional audio
        print("\n[Step 1/5] Generating synthetic test audio (fictional story)...")
        generate_synthetic_audio(synthetic_wav)
        size_bytes, duration_sec = validate_audio(synthetic_wav)
        print(f"  Synthetic Audio File: {synthetic_wav.name}")
        print(f"  File Size:            {size_bytes / 1024:.1f} KiB")
        print(f"  Decoded Duration:     {duration_sec:.2f} seconds")
        print(f"  Text Source:          Fictional narrative (zero personal data)")

        # Step 2: Real whisper.cpp transcription
        print("\n[Step 2/5] Running real local whisper.cpp speech recognition...")
        start_t = time.time()
        segments = transcribe_audio_file(synthetic_wav)
        whisper_elapsed = time.time() - start_t
        print(f"  Transcription Time:   {whisper_elapsed:.2f} seconds (Metal GPU accelerated)")
        print(f"  Segments Detected:    {len(segments)}")

        print("\n  --- Real Timestamped Transcript Segments ---")
        segment_dict = {}
        segment_objs = []
        for seg in segments:
            seg_id = f"seg-{seg.segment_index:03d}"
            segment_dict[seg_id] = seg.text
            segment_objs.append({
                "id": seg_id,
                "segment_index": seg.segment_index,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "text": seg.text,
            })
            start_s = seg.start_ms / 1000.0
            end_s = seg.end_ms / 1000.0
            print(f"  [{seg_id}] ({start_s:05.2f}s -> {end_s:05.2f}s): {seg.text}")

        # Step 3: Real local Qwen extraction via Ollama
        print("\n[Step 3/5] Extracting structured memory cards via local Qwen2.5:1.5b...")
        start_q = time.time()
        raw_cards = extract_memories_from_segments(segment_objs)
        qwen_elapsed = time.time() - start_q
        print(f"  Extraction Time:      {qwen_elapsed:.2f} seconds")
        print(f"  Memory Cards Found:   {len(raw_cards)}")

        # Step 4: Validate evidence and grounding
        print("\n[Step 4/5] Validating source evidence citations against transcript...")
        grounded_cards = validate_memory_cards_batch(raw_cards, segment_dict)

        print(f"\n  --- Verified Grounded Memory Cards ---")
        for i, card in enumerate(grounded_cards, 1):
            print(f"\n  [Memory Card #{i}]")
            print(f"    Title:       {card.title}")
            print(f"    Summary:     {card.summary}")
            print(f"    Themes:      {', '.join(card.themes)}")
            print(f"    Citations:   {card.source_segment_ids}")
            print(f"    Supporting Passages from Recording:")
            for sid, passage in zip(card.source_segment_ids, card.supporting_passages):
                print(f"      - [{sid}]: \"{passage}\"")

        # Step 5: Test rejection of hallucinated / invalid evidence
        print("\n[Step 5/5] Testing anti-hallucination & provenance rejection gates...")

        # Test A: Card citing nonexistent segment
        fake_card_1 = RawMemoryCard(
            title="Invented Family Dinner",
            summary="Arthur made soup for dinner.",
            themes=["cooking"],
            source_segment_ids=["seg-999"],  # Nonexistent!
        )
        try:
            validate_card_evidence(fake_card_1, segment_dict)
            print("  [ERROR] Fake segment citation was NOT rejected!")
            return 1
        except EvidenceValidationError as e:
            print(f"  [PASS] Nonexistent segment reference correctly rejected: ({e.code}) {e.message}")

        # Test B: Card with unsupported verbatim quotation
        fake_card_2 = RawMemoryCard(
            title="Sailing Wisdom",
            summary='Arthur shouted "We will always conquer the stormy Atlantic ocean!"',
            themes=["adventure"],
            source_segment_ids=["seg-000"],
        )
        try:
            validate_card_evidence(fake_card_2, segment_dict)
            print("  [ERROR] Unsupported quotation was NOT rejected!")
            return 1
        except EvidenceValidationError as e:
            print(f"  [PASS] Fabricated quotation correctly rejected: ({e.code}) {e.message}")

        print("\n" + "=" * 65)
        print(" [SUCCESS] EchoArchive Phase A Real Local AI Proof Verified!")
        print("=" * 65)
        return 0

    finally:
        if synthetic_wav.exists():
            synthetic_wav.unlink()


if __name__ == "__main__":
    sys.exit(main())
