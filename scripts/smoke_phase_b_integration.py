"""Real local backend integration verification for EchoArchive Phase B.

Executes a complete, genuine offline audio ingestion, transcription,
persistence, review, and revision-controlled correction workflow on localhost.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from backend.config import DATA_DIR, MEDIA_DIR, ORIGINAL_TRANSCRIPTS_DIR, TMP_DIR, ensure_storage_directories
from backend.database import init_db
from backend.evidence import validate_memory_cards_batch
from backend.extraction import extract_memories_from_segments
from backend.main import app
from backend.media import normalize_to_whisper_wav


def main():
    print("=" * 65)
    print(" EchoArchive — Phase B Real Local Ingestion & Transcription Proof")
    print("=" * 65)

    ensure_storage_directories()
    init_db()

    with TestClient(app) as client:
        # Step 1: Synthesize fictional spoken test audio
        print("\n[Step 1/8] Generating synthetic fictional test audio (macOS say)...")
        fictional_narrative = (
            "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop in coastal Maine. "
            "Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. "
            "He always told me that patience is like trimming the sail: you cannot control the wind, but you can always guide your boat."
        )

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
            raw_aiff_path = Path(tmp_aiff.name)

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        test_wav_path = TMP_DIR / "phase_b_fictional_test.wav"

        try:
            subprocess.run(
                ["say", "-v", "Samantha", "-o", str(raw_aiff_path), fictional_narrative],
                check=True,
                capture_output=True,
            )
            normalize_to_whisper_wav(raw_aiff_path, test_wav_path)
            audio_size = test_wav_path.stat().st_size
            print(f"  Generated Audio File: {test_wav_path.name}")
            print(f"  File Size:            {audio_size / 1024:.1f} KiB")

            # Step 2: Upload story with explicit permission confirmation
            print("\n[Step 2/8] Uploading audio with affirmative consent (POST /api/stories)...")
            with open(test_wav_path, "rb") as af:
                upload_resp = client.post(
                    "/api/stories",
                    data={
                        "title": "Grandfather's Wooden Sailboat",
                        "speaker_label": "Arthur's Grandchild",
                        "permission_confirmed": "true",
                    },
                    files={"audio": ("fictional_narrative.wav", af, "audio/wav")},
                )

            assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
            story_data = upload_resp.json()
            story_id = story_data["id"]
            print(f"  [PASS] Story Created: ID = {story_id}")
            print(f"         Title:         {story_data['title']}")
            print(f"         Revision:      {story_data['transcript_revision']}")
            print(f"         Duration:      {story_data['audio_duration_ms'] / 1000:.2f}s")

            # Verify media file exists in private storage
            story_detail = client.get(f"/api/stories/{story_id}").json()
            stored_audio = DATA_DIR / story_detail["audio_relpath"]
            assert stored_audio.exists(), f"Stored audio file does not exist at {stored_audio}"
            print(f"  [PASS] Stored Audio:   {story_detail['audio_relpath']} (Verified present)")

            # Step 3: Enqueue transcription job
            print("\n[Step 3/8] Enqueuing offline transcription job (POST /api/stories/{id}/transcribe)...")
            t_start = time.time()
            job_resp = client.post(f"/api/stories/{story_id}/transcribe")
            assert job_resp.status_code == 202, f"Failed to enqueue: {job_resp.text}"
            job_data = job_resp.json()
            job_id = job_data["job_id"]
            print(f"  [PASS] Job Accepted:  Job ID = {job_id}, Initial Stage = {job_data['stage']}")

            # Step 4: Poll job status and observe real transitions
            print("\n[Step 4/8] Polling job state transitions (GET /api/jobs/{job_id})...")
            observed_stages = set()
            final_job = None
            for _ in range(60):
                status_resp = client.get(f"/api/jobs/{job_id}")
                assert status_resp.status_code == 200
                current_job = status_resp.json()
                stage = current_job["stage"]
                if stage not in observed_stages:
                    observed_stages.add(stage)
                    print(f"  -> Observed Stage: [{current_job['status'].upper()}] {stage}")

                if current_job["status"] in ("succeeded", "failed"):
                    final_job = current_job
                    break
                time.sleep(0.3)

            t_elapsed = time.time() - t_start
            assert final_job is not None, "Job did not complete within timeout."
            assert final_job["status"] == "succeeded", f"Job failed: {final_job.get('error_message')}"
            print(f"  [PASS] Whisper Transcription Succeeded in {t_elapsed:.2f}s")

            # Step 5: Retrieve persisted transcript segments
            print("\n[Step 5/8] Retrieving persisted transcript segments (GET /api/stories/{id}/segments)...")
            seg_resp = client.get(f"/api/stories/{story_id}/segments")
            assert seg_resp.status_code == 200
            seg_data = seg_resp.json()
            segments = seg_data["segments"]
            print(f"  Story Revision:     {seg_data['transcript_revision']}")
            print(f"  Segments Persisted: {len(segments)}")

            # Find the segment with the Maine transcription error
            target_segment = None
            for s in segments:
                print(f"    [{s['id']}] ({s['start_ms']/1000:05.2f}s -> {s['end_ms']/1000:05.2f}s): {s['text']}")
                if "main" in s["text"].lower():
                    target_segment = s

            assert target_segment is not None, "Expected segment containing 'Main' or 'Maine' not found."
            print(f"\n  Identified target segment for review: [{target_segment['id']}] '{target_segment['text']}'")

            # Step 6: Human review correction and revision increment
            print("\n[Step 6/8] Correcting transcription error (PATCH /api/stories/{id}/segments/{seg_id})...")
            corrected_text = "in coastal Maine."
            correct_resp = client.patch(
                f"/api/stories/{story_id}/segments/{target_segment['id']}",
                json={"text": corrected_text, "expected_revision": 1},
            )
            assert correct_resp.status_code == 200, f"Correction failed: {correct_resp.text}"
            corrected_data = correct_resp.json()
            assert corrected_data["transcript_revision"] == 2
            assert corrected_data["segment"]["user_edited"] == 1
            assert corrected_data["segment"]["text"] == corrected_text
            print(f"  [PASS] Segment Corrected: '{target_segment['text']}' -> '{corrected_text}'")
            print(f"  [PASS] Revision Incremented: 1 -> {corrected_data['transcript_revision']}")

            # Step 7: Optimistic concurrency check (reject stale revision)
            print("\n[Step 7/8] Verifying optimistic concurrency rejection (stale expected_revision=1)...")
            stale_resp = client.patch(
                f"/api/stories/{story_id}/segments/{target_segment['id']}",
                json={"text": "another correction attempt", "expected_revision": 1},
            )
            assert stale_resp.status_code == 409
            stale_err = stale_resp.json()["error"]
            assert stale_err["code"] == "REVISION_CONFLICT"
            print(f"  [PASS] Stale update correctly rejected: HTTP 409 ({stale_err['code']}) {stale_err['message']}")

            # Confirm original machine transcript file remains intact
            orig_file = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"
            assert orig_file.exists(), "Original transcript backup not found."
            with open(orig_file, "r") as f:
                orig_json = json.load(f)
            orig_seg_texts = [s["text"] for s in orig_json["segments"]]
            assert any("main" in t.lower() for t in orig_seg_texts)
            print("  [PASS] Immutable original transcript preserved in data/original_transcripts/")

            # Confirm original audio remains unmodified
            assert stored_audio.stat().st_size == audio_size
            print(f"  [PASS] Original audio file ({stored_audio.name}) remains completely intact ({audio_size} bytes)")

            # Step 8: Phase A compatibility smoke test with Qwen extraction
            print("\n[Step 8/8] Re-running Phase A Qwen memory extraction on corrected transcript...")
            updated_segs = client.get(f"/api/stories/{story_id}/segments").json()["segments"]
            raw_cards = extract_memories_from_segments(updated_segs)
            assert len(raw_cards) >= 1
            segment_dict = {s["id"]: s["text"] for s in updated_segs}
            grounded_cards = validate_memory_cards_batch(raw_cards, segment_dict)
            assert len(grounded_cards) >= 1
            print(f"  [PASS] Qwen extracted {len(grounded_cards)} grounded memory card(s) from corrected transcript:")
            for card in grounded_cards:
                print(f"         Card: '{card.title}'")
                print(f"         Summary: {card.summary}")
                print(f"         Citations: {card.source_segment_ids}")

            print("\n" + "=" * 65)
            print(" [SUCCESS] EchoArchive Phase B Real Local Integration Verified!")
            print("=" * 65)

        finally:
            if raw_aiff_path.exists():
                raw_aiff_path.unlink()
            if test_wav_path.exists():
                test_wav_path.unlink()


if __name__ == "__main__":
    main()
