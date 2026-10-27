"""Live integration tests running genuine local whisper.cpp and Qwen inference."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.config import TMP_DIR
from backend.evidence import validate_memory_cards_batch
from backend.extraction import (
    check_ollama_available,
    check_qwen_model_available,
    extract_memories_from_segments,
)
from backend.media import normalize_to_whisper_wav
from backend.transcription import (
    check_whisper_available,
    check_whisper_model_available,
    transcribe_audio_file,
)


@pytest.mark.live
def test_genuine_local_speech_and_memory_pipeline():
    """
    Test real local AI pipeline with synthetic fictional speech:
    Synthetic Speech -> whisper-cli -> Qwen2.5:1.5b via Ollama -> Grounded Memory Cards.
    """
    if not (check_whisper_available() and check_whisper_model_available()):
        pytest.skip("whisper.cpp or model not available for live test")

    if not (check_ollama_available() and check_qwen_model_available()):
        pytest.skip("Ollama or Qwen2.5 model not available for live test")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
        aiff_path = Path(tmp_aiff.name)

    test_wav = TMP_DIR / "live_test_synthetic.wav"

    fictional_text = (
        "When I was nine years old in Vermont, my aunt Clara taught me how to tap maple trees in early spring. "
        "We collected the sap in metal buckets and boiled it down into golden syrup over wood fire."
    )

    try:
        # 1. Synthesize audio
        subprocess.run(
            ["say", "-v", "Samantha", "-o", str(aiff_path), fictional_text],
            check=True,
            capture_output=True,
        )
        normalize_to_whisper_wav(aiff_path, test_wav)

        # 2. Real whisper transcription
        segments = transcribe_audio_file(test_wav)
        assert len(segments) > 0

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
            # Verify timestamps are ordered and non-negative
            assert seg.start_ms >= 0
            assert seg.end_ms > seg.start_ms

        # 3. Real local Qwen extraction
        cards = extract_memories_from_segments(segment_objs)
        assert len(cards) >= 1

        # 4. Verify evidence grounding
        grounded_cards = validate_memory_cards_batch(cards, segment_dict)
        assert len(grounded_cards) >= 1

        for card in grounded_cards:
            assert len(card.title) > 0
            assert len(card.summary) > 0
            assert len(card.source_segment_ids) > 0
            assert len(card.supporting_passages) == len(card.source_segment_ids)

    finally:
        if aiff_path.exists():
            aiff_path.unlink()
        if test_wav.exists():
            test_wav.unlink()
