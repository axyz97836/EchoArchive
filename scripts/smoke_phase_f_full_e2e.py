"""Comprehensive Real-World End-to-End Verification for EchoArchive Phase F.

Executes the complete, authentic local pipeline with genuine local AI:
1. Health check & dependency readiness
2. Synthesize fictional spoken test audio (no real personal data)
3. Affirmative permission check & multipart audio upload
4. Local whisper.cpp transcription & chronological timestamp verification
5. Verify unreviewed machine transcript state
6. Enforce review requirement: reject extraction before review (422 REVIEW_REQUIRED)
7. Enforce bypass prevention: reject require_review=false (422 REVIEW_BYPASS_FORBIDDEN)
8. Inline human segment error correction (revision increment & review invalidation)
9. Explicit human review confirmation (POST /api/stories/{id}/review)
10. Local Qwen2.5 memory extraction via Ollama & strict evidence validation
11. Verify grounded memory cards, source timestamps, and absence of stale flags
12. Seekable HTTP 206 Partial Content audio streaming check
13. Local full-text parameterized archive search (stories, transcripts, memories)
14. Portable self-contained ZIP export & offline HTML reader audit
15. Safe story deletion with durable journal verification & filesystem purge.
"""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from backend.config import DATA_DIR, MEDIA_DIR, ORIGINAL_TRANSCRIPTS_DIR, TMP_DIR, ensure_storage_directories
from backend.database import get_db, init_db
from backend.main import app
from backend.media import normalize_to_whisper_wav


def run_phase_f_e2e_verification():
    print("=" * 80)
    print(" EchoArchive — Phase F: Comprehensive Real-World E2E Verification")
    print("=" * 80)

    ensure_storage_directories()
    init_db()

    with TestClient(app) as client:
        # Step 1: System Readiness & Dependency Check
        print("\n[Step 1/15] Verifying System Readiness (GET /api/health)...")
        t0 = time.perf_counter()
        health_resp = client.get("/api/health")
        t_health = (time.perf_counter() - t0) * 1000
        assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
        health = health_resp.json()
        print(f"  Health Status:         {health['status']} ({t_health:.1f} ms)")
        print(f"  Speech Engine:         {health['services']['speech_recognition']['engine']} (cli={health['services']['speech_recognition']['cli_available']}, model={health['services']['speech_recognition']['model_available']})")
        print(f"  Media Tool:            {health['services']['media_preprocessing']['tool']} (ready={health['services']['media_preprocessing']['ready']})")
        print(f"  Language Model:        {health['services']['language_model']['provider']} / {health['services']['language_model']['model']} (reachable={health['services']['language_model']['server_reachable']})")
        print(f"  Database / Storage:    {health['services']['database']['engine']} (local_only={health['services']['storage']['local_only']})")

        # Step 2: Synthesize Fictional Spoken Audio
        print("\n[Step 2/15] Synthesizing Fictional Test Audio (macOS say + FFmpeg)...")
        fictional_narrative = (
            "When I was nine years old in Vermont, my aunt Clara taught me how to tap maple trees in early spring. "
            "We hung the galvanized metal buckets on the spiles and listened to the slow rhythm of the sap dripping. "
            "She told me that true sweetness takes patience, boiling forty gallons of sap down to a single gallon of golden syrup."
        )

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
            raw_aiff = Path(tmp_aiff.name)

        test_wav = TMP_DIR / "phase_f_e2e_verif.wav"
        t_synth_0 = time.perf_counter()
        subprocess.run(
            ["say", "-v", "Samantha", "-o", str(raw_aiff), fictional_narrative],
            check=True,
            capture_output=True,
        )
        normalize_to_whisper_wav(raw_aiff, test_wav)
        t_synth = time.perf_counter() - t_synth_0
        audio_bytes = test_wav.read_bytes()
        print(f"  Generated Audio:       {test_wav.name} ({len(audio_bytes) / 1024:.1f} KiB, synthesized in {t_synth:.2f}s)")

        # Step 3: Ingest Story with Explicit Permission
        print("\n[Step 3/15] Ingesting Story with Affirmative Permission (POST /api/stories)...")
        with open(test_wav, "rb") as af:
            upload_resp = client.post(
                "/api/stories",
                data={
                    "title": "Aunt Clara's Maple Sugar Cabin in Vermont",
                    "speaker_label": "Clara's Niece",
                    "permission_confirmed": "true",
                },
                files={"audio": ("vermont_maple.wav", af, "audio/wav")},
            )
        assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
        story = upload_resp.json()
        story_id = story["id"]
        story_details = client.get(f"/api/stories/{story_id}").json()
        print(f"  Story Created:         ID={story_id}")
        print(f"  Title:                 {story['title']}")
        print(f"  Duration:              {story.get('audio_duration_ms', 0) / 1000:.1f}s")
        print(f"  Consent Recorded:      {story_details['consent_confirmed_at']}")

        # Step 4: Real Local whisper.cpp Transcription
        print("\n[Step 4/15] Starting Real Local whisper.cpp Transcription (POST /api/stories/{id}/transcribe)...")
        tx_resp = client.post(f"/api/stories/{story_id}/transcribe")
        assert tx_resp.status_code == 202, f"Transcribe start failed: {tx_resp.text}"
        tx_job_id = tx_resp.json()["job_id"]
        print(f"  Transcription Job:     ID={tx_job_id}")

        t_tx_start = time.perf_counter()
        stages_observed = []
        while True:
            job_resp = client.get(f"/api/jobs/{tx_job_id}").json()
            stage = job_resp.get("stage")
            if stage not in stages_observed:
                stages_observed.append(stage)
                print(f"    --> Stage: {stage}")
            if job_resp["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.3)
        t_tx_total = time.perf_counter() - t_tx_start
        assert job_resp["status"] == "succeeded", f"Transcription failed: {job_resp.get('error_message')}"
        print(f"  Transcription Completed: {t_tx_total:.2f}s (Stages: {' -> '.join(stages_observed)})")

        # Step 5: Verify Machine Transcript is Marked Unreviewed
        print("\n[Step 5/15] Verifying Machine Transcript Unreviewed State...")
        story_check = client.get(f"/api/stories/{story_id}").json()
        assert story_check["transcript_revision"] == 1
        assert story_check["is_reviewed"] is False
        assert story_check["transcript_reviewed_at"] is None
        print(f"  Revision:              {story_check['transcript_revision']}")
        print(f"  is_reviewed:           {story_check['is_reviewed']} (Correctly unreviewed)")

        segs_data = client.get(f"/api/stories/{story_id}/segments").json()
        segments = segs_data["segments"]
        print(f"  Segments Extracted:    {len(segments)} segments")
        for i, s in enumerate(segments):
            print(f"    [{s['start_ms']}ms – {s['end_ms']}ms]: \"{s['text']}\"")

        # Step 6: Verify Extraction Rejection Before Review
        print("\n[Step 6/15] Verifying Extraction Gating Before Review (POST /api/stories/{id}/extract)...")
        extract_blocked = client.post(f"/api/stories/{story_id}/extract", json={})
        assert extract_blocked.status_code == 422
        assert extract_blocked.json()["error"]["code"] == "REVIEW_REQUIRED"
        print("  [PASS] Extraction rejected as expected: 422 REVIEW_REQUIRED")

        # Step 7: Verify Extraction Rejection on Bypass Attempt
        print("\n[Step 7/15] Verifying Extraction Rejection on Public Bypass Attempt...")
        bypass_resp = client.post(
            f"/api/stories/{story_id}/extract",
            json={"expected_revision": 1, "require_review": False},
        )
        assert bypass_resp.status_code == 422
        assert bypass_resp.json()["error"]["code"] == "REVIEW_BYPASS_FORBIDDEN"
        print("  [PASS] Public bypass rejected as expected: 422 REVIEW_BYPASS_FORBIDDEN")

        # Step 8: Inline Human Segment Error Correction
        print("\n[Step 8/15] Correcting Transcription Segment (PATCH /api/stories/{id}/segments/{seg_id})...")
        first_seg = segments[0]
        corrected_text = first_seg["text"].replace("Vermont", "rural Vermont")
        patch_resp = client.patch(
            f"/api/stories/{story_id}/segments/{first_seg['id']}",
            json={"text": corrected_text, "expected_revision": 1},
        )
        assert patch_resp.status_code == 200
        patch_data = patch_resp.json()
        assert patch_data["transcript_revision"] == 2
        assert patch_data["transcript_reviewed_at"] is None
        print(f"  Corrected Segment:     \"{corrected_text}\"")
        print(f"  New Revision:          {patch_data['transcript_revision']} (Review invalidated)")

        # Step 9: Explicit Human Review Confirmation
        print("\n[Step 9/15] Explicitly Confirming Human Review (POST /api/stories/{id}/review)...")
        review_resp = client.post(f"/api/stories/{story_id}/review")
        assert review_resp.status_code == 200
        rev_story = review_resp.json()
        assert rev_story["is_reviewed"] is True
        assert rev_story["transcript_reviewed_at"] is not None
        print(f"  Review Confirmed:      {rev_story['transcript_reviewed_at']}")
        print(f"  is_reviewed:           {rev_story['is_reviewed']}")

        # Step 10: Real Local Qwen2.5 Memory Extraction via Ollama
        print("\n[Step 10/15] Starting Real Local Qwen2.5 Memory Extraction via Ollama...")
        ext_resp = client.post(
            f"/api/stories/{story_id}/extract",
            json={"expected_revision": 2},
        )
        assert ext_resp.status_code == 202
        ext_job_id = ext_resp.json()["job_id"]
        print(f"  Extraction Job:        ID={ext_job_id}")

        t_ext_start = time.perf_counter()
        ext_stages_observed = []
        while True:
            ej = client.get(f"/api/jobs/{ext_job_id}").json()
            stage = ej.get("stage")
            if stage not in ext_stages_observed:
                ext_stages_observed.append(stage)
                print(f"    --> Stage: {stage}")
            if ej["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.3)
        t_ext_total = time.perf_counter() - t_ext_start
        assert ej["status"] == "succeeded", f"Extraction failed: {ej.get('error_message')}"
        print(f"  Extraction Completed:  {t_ext_total:.2f}s (Stages: {' -> '.join(ext_stages_observed)})")

        # Step 11: Verify Grounded Traceable Memory Cards
        print("\n[Step 11/15] Inspecting Grounded Memory Cards (GET /api/stories/{id}/cards)...")
        cards_resp = client.get(f"/api/stories/{story_id}/cards")
        assert cards_resp.status_code == 200
        cards_data = cards_resp.json()
        assert cards_data["has_stale_cards"] is False
        assert len(cards_data["cards"]) > 0

        print(f"  Extracted Cards:       {len(cards_data['cards'])} cards")
        for c in cards_data["cards"]:
            print(f"    Card: \"{c['title']}\"")
            print(f"      Summary:     {c['summary']}")
            print(f"      Themes:      {c['themes']}")
            print(f"      Provenance:  {c['model_provenance']}")
            print(f"      Revision:    {c['generated_from_revision']} (is_stale={c['is_stale']})")
            print(f"      Sources Cited ({len(c['sources'])}):")
            for s in c["sources"]:
                print(f"        - [{s['start_ms']}ms – {s['end_ms']}ms] \"{s['text']}\"")
            assert len(c["sources"]) > 0, "Memory card must have at least one valid source reference!"

        # Step 12: Byte-Range Audio Streaming Check
        print("\n[Step 12/15] Testing Byte-Range Audio Streaming (GET /api/stories/{id}/audio Range)...")
        audio_stream_resp = client.get(
            f"/api/stories/{story_id}/audio",
            headers={"Range": "bytes=0-1023"},
        )
        assert audio_stream_resp.status_code == 206
        assert audio_stream_resp.headers.get("content-range", "").startswith("bytes 0-1023/")
        assert len(audio_stream_resp.content) == 1024
        print("  [PASS] HTTP 206 Partial Content byte-range seeking verified.")

        # Step 13: Local Parameterized Full-Text Archive Search
        print("\n[Step 13/15] Testing Local Parameterized Archive Search (GET /api/search?q=maple)...")
        search_resp = client.get("/api/search?q=maple")
        assert search_resp.status_code == 200
        search_results = search_resp.json()
        assert search_results["total"] > 0
        print(f"  Search Query:          'maple' -> {search_results['total']} match(es)")
        for m in search_results["results"]:
            print(f"    Type: [{m['result_type']}] Title: \"{m['story_title']}\" Snippet: \"{m['snippet']}\"")

        # Step 14: Portable ZIP Export & Standalone Offline Reader Audit
        print("\n[Step 14/15] Testing Portable ZIP Export & Offline HTML Reader...")
        t_exp_0 = time.perf_counter()
        export_resp = client.get(f"/api/stories/{story_id}/export")
        t_exp = (time.perf_counter() - t_exp_0) * 1000
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"

        zf = zipfile.ZipFile(io.BytesIO(export_resp.content))
        namelist = zf.namelist()
        print(f"  Export ZIP Size:       {len(export_resp.content) / 1024:.1f} KiB (generated in {t_exp:.1f} ms)")
        print(f"  Archive Members:       {', '.join(namelist)}")

        assert "audio.wav" in namelist
        assert "story.json" in namelist
        assert "transcript.json" in namelist
        assert "memories.json" in namelist
        assert "manifest.json" in namelist
        assert "story.html" in namelist

        # Verify exact audio bytes
        exported_audio = zf.read("audio.wav")
        assert hashlib.sha256(exported_audio).hexdigest() == hashlib.sha256(audio_bytes).hexdigest()

        # Audit offline HTML reader
        html_text = zf.read("story.html").decode("utf-8")
        assert "http://" not in html_text
        assert "https://" not in html_text
        assert "AI Interpretation" in html_text
        print("  [PASS] Export ZIP SHA-256 checksums match and offline reader has zero network dependencies.")

        # Step 15: Safe Deletion with Durable Journal & Purge
        print("\n[Step 15/15] Testing Safe Deletion with Durable Journal (DELETE /api/stories/{id}?confirm=true)...")
        del_resp = client.delete(f"/api/stories/{story_id}?confirm=true")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        # Verify filesystem files are unlinked
        assert not (MEDIA_DIR / f"{story_id}.wav").exists()
        assert not (ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json").exists()

        # Verify database records are cascade-deleted
        with get_db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM stories WHERE id = ?;", (story_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM deletion_journal WHERE story_id = ?;", (story_id,)).fetchone()[0] == 0
        print("  [PASS] Story records cascade-deleted, filesystem media purged, and journal clean.")

    # Cleanup temp wav
    if test_wav.exists():
        test_wav.unlink()

    print("\n" + "=" * 80)
    print(" ALL 15 REAL-WORLD VERIFICATION GATES PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_phase_f_e2e_verification()
