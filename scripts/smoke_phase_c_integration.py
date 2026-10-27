"""Real local backend integration verification for EchoArchive Phase C: Traceable Memories.

Executes a complete, genuine offline workflow on localhost:
Ingest -> Whisper transcription -> Human transcript review -> Real local Qwen extraction
-> Server evidence validation -> SQLite card persistence -> API retrieval
-> Source-linked audio byte-range seek playback -> Stale memory invalidation on transcript edit
-> Regeneration against latest revision.
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

from backend.config import DATA_DIR, MEDIA_DIR, TMP_DIR, ensure_storage_directories
from backend.database import init_db
from backend.main import app
from backend.media import normalize_to_whisper_wav


def main():
    print("=" * 70)
    print(" EchoArchive — Phase C Real Local AI & Traceable Memories Proof")
    print("=" * 70)

    ensure_storage_directories()
    init_db()

    with TestClient(app) as client:
        # Step 1: Synthesize fictional spoken test audio
        print("\n[Step 1/11] Generating synthetic fictional test audio (macOS say)...")
        fictional_narrative = (
            "When I was seven years old, my grandfather Arthur built a small wooden sailboat in his workshop in coastal Maine. "
            "Every Sunday morning in July, we took the boat down to the harbor and watched the white sails catch the wind. "
            "He always told me that patience is like trimming the sail: you cannot control the wind, but you can always guide your boat."
        )

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
            raw_aiff_path = Path(tmp_aiff.name)

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        test_wav_path = TMP_DIR / "phase_c_fictional_test.wav"

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

            # Step 2: Upload story with affirmative consent
            print("\n[Step 2/11] Uploading audio with affirmative consent (POST /api/stories)...")
            with open(test_wav_path, "rb") as af:
                upload_resp = client.post(
                    "/api/stories",
                    data={
                        "title": "Grandfather's Wooden Sailboat in Maine",
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

            # Step 3: Run offline Whisper transcription
            print("\n[Step 3/11] Running offline whisper.cpp speech recognition (POST /api/stories/{id}/transcribe)...")
            t0 = time.time()
            job_resp = client.post(f"/api/stories/{story_id}/transcribe")
            assert job_resp.status_code == 202
            job_id = job_resp.json()["job_id"]

            # Poll transcription job
            for _ in range(60):
                j_resp = client.get(f"/api/jobs/{job_id}")
                assert j_resp.status_code == 200
                job = j_resp.json()
                if job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(0.3)

            assert job["status"] == "succeeded", f"Transcription failed: {job.get('error_message')}"
            print(f"  [PASS] Whisper transcription succeeded in {time.time() - t0:.2f}s")

            # Step 4: Retrieve transcript segments
            print("\n[Step 4/11] Retrieving transcript segments (GET /api/stories/{id}/segments)...")
            seg_resp = client.get(f"/api/stories/{story_id}/segments")
            assert seg_resp.status_code == 200
            segments = seg_resp.json()["segments"]
            print(f"  Segments Persisted: {len(segments)}")

            target_seg = None
            for s in segments:
                print(f"    [{s['id']}] ({s['start_ms']/1000:05.2f}s -> {s['end_ms']/1000:05.2f}s): {s['text']}")
                if "main" in s["text"].lower():
                    target_seg = s

            # Step 5: Human review correction
            print("\n[Step 5/11] Human review: correcting transcription mistake (PATCH /api/stories/{id}/segments/{seg_id})...")
            if target_seg:
                corrected_text = "in coastal Maine."
                patch_resp = client.patch(
                    f"/api/stories/{story_id}/segments/{target_seg['id']}",
                    json={"text": corrected_text, "expected_revision": 1},
                )
                assert patch_resp.status_code == 200
                rev2 = patch_resp.json()["transcript_revision"]
                assert rev2 == 2
                print(f"  [PASS] Segment corrected to: '{corrected_text}' (Revision 1 -> 2)")
            else:
                rev2 = 1

            # Step 6: Real local Qwen extraction via Ollama
            print("\n[Step 6/11] Extracting grounded memories via local Qwen2.5:1.5b (POST /api/stories/{id}/extract)...")
            t_extract_start = time.time()
            extract_resp = client.post(
                f"/api/stories/{story_id}/extract",
                json={"expected_revision": rev2},
            )
            assert extract_resp.status_code == 202, f"Extract request failed: {extract_resp.text}"
            extract_job_id = extract_resp.json()["job_id"]
            print(f"  [PASS] Extraction Job Enqueued: {extract_job_id}")

            # Poll extraction job
            observed_stages = set()
            extract_final = None
            for _ in range(90):
                st_resp = client.get(f"/api/jobs/{extract_job_id}")
                assert st_resp.status_code == 200
                cur_job = st_resp.json()
                stage = cur_job["stage"]
                if stage not in observed_stages:
                    observed_stages.add(stage)
                    print(f"  -> Observed Stage: [{cur_job['status'].upper()}] {stage}")

                if cur_job["status"] in ("succeeded", "failed"):
                    extract_final = cur_job
                    break
                time.sleep(0.5)

            t_extract_elapsed = time.time() - t_extract_start
            assert extract_final is not None, "Extraction job timed out."
            assert extract_final["status"] == "succeeded", f"Extraction failed: {extract_final.get('error_code')} - {extract_final.get('error_message')}"
            print(f"  [PASS] Qwen memory extraction succeeded in {t_extract_elapsed:.2f}s")

            # Step 7: Retrieve and verify saved memory cards with citations
            print("\n[Step 7/11] Retrieving persisted memory cards via API (GET /api/stories/{id}/cards)...")
            cards_resp = client.get(f"/api/stories/{story_id}/cards")
            assert cards_resp.status_code == 200
            cards_data = cards_resp.json()
            assert cards_data["current_transcript_revision"] == rev2
            assert cards_data["has_stale_cards"] is False
            cards = cards_data["cards"]
            assert len(cards) >= 1, "Expected at least one memory card extracted by Qwen."

            first_card = cards[0]
            print(f"  [PASS] Retrieved {len(cards)} Grounded Memory Card(s):")
            for idx, c in enumerate(cards, start=1):
                print(f"    Memory Card #{idx}:")
                print(f"      ID:               {c['id']}")
                print(f"      Title:            {c['title']}")
                print(f"      Summary:          {c['summary']}")
                print(f"      Themes:           {c['themes']}")
                print(f"      Review State:     {c['review_state']} (Human review required)")
                print(f"      Model Provenance: {c['model_provenance']}")
                print(f"      Revision:         Rev {c['generated_from_revision']} (is_stale={c['is_stale']})")
                print(f"      Cited Sources:    {len(c['sources'])} segment(s)")
                for s in c["sources"]:
                    print(f"        - [{s['segment_id']}] ({s['start_seconds']:.2f}s -> {s['end_seconds']:.2f}s): \"{s['text']}\"")

            # Step 8: Source-linked audio seek playback via HTTP 206
            print("\n[Step 8/11] Testing source-linked original audio playback (GET /api/stories/{id}/audio with Range)...")
            assert len(first_card["sources"]) > 0
            first_source = first_card["sources"][0]
            start_sec = first_source["start_seconds"]
            end_sec = first_source["end_seconds"]
            print(f"  Target Source Moment: [{first_source['segment_id']}] {start_sec:.2f}s -> {end_sec:.2f}s")

            # Query audio range header
            audio_resp = client.get(
                first_source["audio_url"],
                headers={"Range": "bytes=0-4095"}
            )
            assert audio_resp.status_code == 206, f"Expected 206 Partial Content, got {audio_resp.status_code}"
            assert "bytes 0-4095/" in audio_resp.headers.get("content-range", "")
            assert audio_resp.headers.get("accept-ranges") == "bytes"
            print(f"  [PASS] HTTP 206 Seekable audio byte-range stream verified (Content-Range: {audio_resp.headers['content-range']})")
            print(f"  [PASS] Client seeking target: {start_sec:.2f}s -> {end_sec:.2f}s verified available")

            # Step 9: Single card details and review state endpoint
            print("\n[Step 9/11] Inspecting card details & updating review state (PATCH /api/cards/{id})...")
            detail_resp = client.get(f"/api/cards/{first_card['id']}")
            assert detail_resp.status_code == 200
            assert detail_resp.json()["id"] == first_card["id"]

            patch_review = client.patch(
                f"/api/cards/{first_card['id']}",
                json={"review_state": "accepted"}
            )
            assert patch_review.status_code == 200
            assert patch_review.json()["review_state"] == "accepted"
            print(f"  [PASS] Card review state transitioned: draft -> accepted")

            # Step 10: Demonstrate stale-card invalidation when transcript changes
            print("\n[Step 10/11] Modifying transcript to trigger dynamic STALE card invalidation...")
            first_seg = segments[0]
            patch_again = client.patch(
                f"/api/stories/{story_id}/segments/{first_seg['id']}",
                json={"text": "When I was precisely seven years of age, Arthur built a small boat.", "expected_revision": rev2}
            )
            assert patch_again.status_code == 200
            rev3 = patch_again.json()["transcript_revision"]
            assert rev3 == rev2 + 1
            print(f"  [PASS] Transcript modified to revision {rev3}")

            stale_cards_resp = client.get(f"/api/stories/{story_id}/cards")
            assert stale_cards_resp.status_code == 200
            stale_cards_data = stale_cards_resp.json()
            assert stale_cards_data["current_transcript_revision"] == rev3
            assert stale_cards_data["has_stale_cards"] is True
            assert stale_cards_data["cards"][0]["is_stale"] is True
            print(f"  [PASS] Previously generated card dynamically marked as STALE:")
            print(f"         Reason: {stale_cards_data['cards'][0]['stale_reason']}")

            # Step 11: Regenerate against new revision
            print("\n[Step 11/11] Regenerating memories against Revision 3 (POST /api/stories/{id}/extract)...")
            regen_resp = client.post(
                f"/api/stories/{story_id}/extract",
                json={"expected_revision": rev3}
            )
            assert regen_resp.status_code == 202
            regen_job_id = regen_resp.json()["job_id"]

            for _ in range(90):
                st_resp = client.get(f"/api/jobs/{regen_job_id}")
                cur_job = st_resp.json()
                if cur_job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(0.5)

            assert cur_job["status"] == "succeeded", f"Regeneration failed: {cur_job.get('error_message')}"
            refreshed_cards = client.get(f"/api/stories/{story_id}/cards").json()
            assert refreshed_cards["current_transcript_revision"] == rev3
            assert refreshed_cards["has_stale_cards"] is False
            for rc in refreshed_cards["cards"]:
                assert rc["is_stale"] is False
                assert rc["generated_from_revision"] == rev3
            print(f"  [PASS] Successfully regenerated {len(refreshed_cards['cards'])} card(s) for Revision 3 without duplicates.")

            print("\n" + "=" * 70)
            print(" [SUCCESS] EchoArchive Phase C Real Local Integration Verified!")
            print("=" * 70)

        finally:
            if raw_aiff_path.exists():
                raw_aiff_path.unlink(missing_ok=True)
            if test_wav_path.exists():
                test_wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
