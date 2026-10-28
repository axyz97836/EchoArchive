"""Portable, self-contained story export archive generator for EchoArchive."""

import hashlib
import html
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import DATA_DIR, MEDIA_DIR, ORIGINAL_TRANSCRIPTS_DIR


class ExportError(Exception):
    """Exception raised when story export fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _sha256_bytes(data: bytes) -> str:
    """Calculate SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def _format_timestamp(ms: int) -> str:
    """Format milliseconds into M:SS or MM:SS."""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def generate_offline_html(
    story: Dict[str, Any],
    segments: List[Dict[str, Any]],
    cards: List[Dict[str, Any]],
    audio_filename: str,
) -> str:
    """
    Generate a self-contained, offline-readable HTML document for the story.
    Uses 'Archive After Dark' visual system with inline CSS.
    Zero external fonts, CDNs, or remote scripts. All text safely escaped.
    """
    title = html.escape(story.get("title") or "Spoken Story")
    speaker = html.escape(story.get("speaker_label") or "Unknown Speaker")
    created = html.escape(story.get("created_at") or "")
    reviewed_at = story.get("transcript_reviewed_at")
    review_status_badge = (
        '<span class="badge badge-success">Human Reviewed</span>'
        if reviewed_at
        else '<span class="badge badge-warning">Review Needed</span>'
    )
    rev_num = story.get("transcript_revision", 0)

    # Build segments HTML
    segments_html_parts = []
    for seg in segments:
        start_str = _format_timestamp(seg.get("start_ms", 0))
        end_str = _format_timestamp(seg.get("end_ms", 0))
        seg_text = html.escape(seg.get("text", ""))
        edited_mark = ' <span class="badge-edited">(corrected)</span>' if seg.get("user_edited") else ""
        seg_id = html.escape(str(seg.get("id", "")))
        segments_html_parts.append(f"""
        <div class="segment" id="{seg_id}">
            <div class="seg-time">{start_str} – {end_str}{edited_mark}</div>
            <div class="seg-text">{seg_text}</div>
        </div>
        """)
    segments_html = "".join(segments_html_parts) if segments_html_parts else "<p class='empty-text'>No transcript segments available.</p>"

    # Build cards HTML
    cards_html_parts = []
    for card in cards:
        card_title = html.escape(card.get("title", ""))
        card_summary = html.escape(card.get("summary", ""))
        is_stale = card.get("is_stale", False)
        provenance = html.escape(card.get("model_provenance") or "Local AI")
        themes = card.get("themes", [])
        themes_html = "".join(f'<span class="theme-tag">{html.escape(t)}</span>' for t in themes)

        stale_badge = '<span class="badge badge-warning">Stale (Transcript Modified)</span>' if is_stale else '<span class="badge badge-neutral">Current Interpretation</span>'
        review_badge = f'<span class="badge badge-info">{html.escape(card.get("review_state", "draft").capitalize())}</span>'
        interpretation_badge = '<span class="badge badge-interpretation">AI Interpretation</span>'

        # Sources
        sources = card.get("sources", [])
        sources_html_parts = []
        for src in sources:
            s_start = _format_timestamp(src.get("start_ms", 0))
            s_end = _format_timestamp(src.get("end_ms", 0))
            s_text = html.escape(src.get("text", ""))
            s_id = html.escape(str(src.get("segment_id", "")))
            sources_html_parts.append(f"""
            <div class="evidence-quote">
                <span class="evidence-time"><a href="#{s_id}">[{s_start} – {s_end}]</a></span>
                <span class="evidence-text">"{s_text}"</span>
            </div>
            """)
        sources_html = "".join(sources_html_parts) if sources_html_parts else "<p class='empty-text'>No source citations.</p>"

        cards_html_parts.append(f"""
        <article class="memory-card{' card-stale' if is_stale else ''}">
            <div class="card-header">
                <h3>{card_title}</h3>
                <div class="card-badges">{stale_badge} {review_badge} {interpretation_badge}</div>
            </div>
            <p class="card-summary">{card_summary}</p>
            <div class="card-themes">{themes_html}</div>
            <div class="card-evidence">
                <div class="evidence-header">Authoritative Spoken Evidence:</div>
                {sources_html}
            </div>
            <div class="card-footer">Model provenance: {provenance} (local inference interpretation)</div>
        </article>
        """)
    cards_html = "".join(cards_html_parts) if cards_html_parts else "<p class='empty-text'>No memory cards extracted.</p>"

    safe_audio_filename = html.escape(audio_filename)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — EchoArchive Portable Export</title>
    <style>
        :root {{
            --bg-base: #141c21;
            --bg-surface: #1b252b;
            --bg-elevated: #243139;
            --text-primary: #f3e8d6;
            --text-muted: #b8c4cb;
            --text-dim: #7d8d96;
            --accent-amber: #e5b65f;
            --accent-burgundy: #8c4b4a;
            --border-subtle: #2d3e48;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-family);
            line-height: 1.6;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 860px;
            margin: 0 auto;
        }}
        header {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
        }}
        .title-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
        }}
        h1 {{
            font-size: 1.85rem;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .meta-line {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-bottom: 1.25rem;
        }}
        .player-wrap {{
            margin-top: 1.25rem;
            padding-top: 1.25rem;
            border-top: 1px solid var(--border-subtle);
        }}
        audio {{
            width: 100%;
            border-radius: 8px;
        }}
        .badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.65rem;
            border-radius: 999px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .badge-success {{ background: #234d38; color: #7ee7a8; border: 1px solid #2e664a; }}
        .badge-warning {{ background: #5c4217; color: #f5cf7b; border: 1px solid #7d591f; }}
        .badge-neutral {{ background: var(--bg-elevated); color: var(--text-muted); border: 1px solid var(--border-subtle); }}
        .badge-info {{ background: #1c3b52; color: #82c8f8; border: 1px solid #275270; }}
        .badge-interpretation {{ background: #3b2a4a; color: #d8b4e2; border: 1px solid #5a3d73; }}
        .badge-edited {{ font-size: 0.75rem; color: var(--accent-amber); font-style: italic; }}

        section {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }}
        h2 {{
            font-size: 1.35rem;
            color: var(--accent-amber);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .section-desc {{
            color: var(--text-dim);
            font-size: 0.88rem;
            margin-bottom: 1.25rem;
        }}
        .segment {{
            padding: 0.85rem;
            border-bottom: 1px solid var(--border-subtle);
            transition: background 0.15s;
        }}
        .segment:last-child {{ border-bottom: none; }}
        .segment:target {{
            background: rgba(229, 182, 95, 0.15);
            border-left: 3px solid var(--accent-amber);
        }}
        .seg-time {{
            font-size: 0.8rem;
            color: var(--text-dim);
            font-family: monospace;
            margin-bottom: 0.25rem;
        }}
        .seg-text {{
            font-size: 1rem;
            color: var(--text-primary);
        }}

        .memory-card {{
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 1.25rem;
            margin-bottom: 1.25rem;
        }}
        .card-stale {{
            border-left: 4px solid var(--accent-burgundy);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
            flex-wrap: wrap;
        }}
        .card-header h3 {{
            font-size: 1.15rem;
            color: var(--text-primary);
        }}
        .card-summary {{
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-bottom: 0.75rem;
        }}
        .card-themes {{
            display: flex;
            gap: 0.4rem;
            flex-wrap: wrap;
            margin-bottom: 0.85rem;
        }}
        .theme-tag {{
            background: rgba(229, 182, 95, 0.12);
            color: var(--accent-amber);
            font-size: 0.75rem;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
        }}
        .card-evidence {{
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 0.75rem;
            margin-bottom: 0.75rem;
        }}
        .evidence-header {{
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 0.4rem;
            letter-spacing: 0.05em;
        }}
        .evidence-quote {{
            font-size: 0.88rem;
            color: var(--text-primary);
            margin-bottom: 0.35rem;
        }}
        .evidence-time a {{
            color: var(--accent-amber);
            text-decoration: none;
            font-family: monospace;
            font-size: 0.8rem;
            margin-right: 0.4rem;
        }}
        .evidence-time a:hover {{ text-decoration: underline; }}
        .card-footer {{
            font-size: 0.75rem;
            color: var(--text-dim);
        }}
        footer {{
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-dim);
            padding: 2rem 0;
        }}
        .empty-text {{
            color: var(--text-dim);
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-row">
                <h1>{title}</h1>
                <div>{review_status_badge}</div>
            </div>
            <div class="meta-line">
                <span>Narrator: <strong>{speaker}</strong></span> &bull;
                <span>Preserved: {created}</span> &bull;
                <span>Transcript Revision: {rev_num}</span>
            </div>
            <div class="player-wrap">
                <audio controls preload="metadata">
                    <source src="./{safe_audio_filename}" type="{html.escape(story.get('audio_media_type', 'audio/wav'))}">
                    Your browser does not support local audio playback.
                </audio>
            </div>
        </header>

        <section>
            <h2>Verified Transcript</h2>
            <div class="section-desc">Authoritative spoken words from the original recording.</div>
            {segments_html}
        </section>

        <section>
            <h2>Traceable Memories</h2>
            <div class="section-desc">Interpretive summaries generated by local AI, grounded strictly in verifiable spoken transcript passages. These are AI interpretations, not direct quotes.</div>
            {cards_html}
        </section>

        <footer>
            Exported from <strong>EchoArchive</strong> &bull; Local-first speech preservation &bull; Self-contained offline reader
        </footer>
    </div>
</body>
</html>"""


def build_story_export_zip(conn: sqlite3.Connection, story_id: str) -> io.BytesIO:
    """
    Generate a complete, portable self-contained ZIP archive in memory for the given story.
    Enforces that active jobs reject export.
    Members:
      - audio.<ext> (original binary audio bytes)
      - story.json (metadata)
      - transcript.json (chronological segments and metadata)
      - memories.json (cards and grounded citations)
      - manifest.json (format echoarchive-export-v1, sha256 checksums)
      - story.html (self-contained offline reader)
    Returns io.BytesIO containing valid ZIP bytes.
    """
    # 1. Fetch story
    story_row = conn.execute("SELECT * FROM stories WHERE id = ?;", (story_id,)).fetchone()
    if not story_row:
        raise ExportError("STORY_NOT_FOUND", f"Story '{story_id}' does not exist.")

    story = dict(story_row)

    # 2. Check for active jobs
    active_job = conn.execute(
        """
        SELECT id, kind, status FROM jobs
        WHERE story_id = ? AND status IN ('queued', 'running');
        """,
        (story_id,),
    ).fetchone()
    if active_job:
        raise ExportError(
            "JOB_ACTIVE",
            f"Cannot export story while a {active_job['kind']} job ({active_job['id']}) is actively processing.",
        )

    # 3. Fetch original audio file
    audio_relpath = story.get("audio_relpath")
    if not audio_relpath:
        raise ExportError("AUDIO_NOT_FOUND", "Story has no audio record associated.")

    audio_disk_path = (DATA_DIR / audio_relpath).resolve()
    # Boundary check
    try:
        audio_disk_path.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        raise ExportError("FORBIDDEN", "Audio path traversal outside media directory.")

    if audio_disk_path.is_symlink():
        raise ExportError("SECURITY_ERROR", "Symlink audio paths are rejected for export.")

    if not audio_disk_path.exists() or not audio_disk_path.is_file():
        raise ExportError("AUDIO_NOT_FOUND", "Original audio recording file is missing from storage.")

    audio_bytes = audio_disk_path.read_bytes()
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise ExportError("PAYLOAD_TOO_LARGE", "Audio recording exceeds maximum permitted export size.")
    audio_ext = audio_disk_path.suffix.lower() or ".wav"
    audio_member_name = f"audio{audio_ext}"

    # 4. Fetch transcript segments
    seg_cursor = conn.execute(
        """
        SELECT id, segment_index, start_ms, end_ms, text, user_edited
        FROM transcript_segments
        WHERE story_id = ?
        ORDER BY segment_index ASC;
        """,
        (story_id,),
    )
    segments = [dict(r) for r in seg_cursor.fetchall()]

    # 5. Fetch memory cards with citations
    current_rev = story.get("transcript_revision", 0)
    cards_cursor = conn.execute(
        """
        SELECT id, story_id, title, summary, themes_json,
               generated_from_revision, review_state, model_provenance, created_at
        FROM memory_cards
        WHERE story_id = ?
        ORDER BY created_at ASC;
        """,
        (story_id,),
    )
    cards = []
    for crow in cards_cursor.fetchall():
        card_id = crow["id"]
        is_stale = (crow["generated_from_revision"] != current_rev)
        themes = []
        try:
            themes = json.loads(crow["themes_json"])
        except Exception:
            themes = []

        # Sources
        sources_cursor = conn.execute(
            """
            SELECT ts.id AS segment_id, ts.segment_index, ts.start_ms, ts.end_ms, ts.text, ts.user_edited
            FROM memory_sources ms
            JOIN transcript_segments ts ON ms.segment_id = ts.id
            WHERE ms.card_id = ? AND ts.story_id = ?
            ORDER BY ts.segment_index ASC;
            """,
            (card_id, story_id),
        )
        sources = [dict(s) for s in sources_cursor.fetchall()]

        cards.append({
            "id": card_id,
            "title": crow["title"],
            "summary": crow["summary"],
            "themes": themes,
            "generated_from_revision": crow["generated_from_revision"],
            "is_stale": is_stale,
            "review_state": crow["review_state"],
            "model_provenance": crow["model_provenance"],
            "created_at": crow["created_at"],
            "sources": sources,
        })

    # Optional: Original machine transcript snapshot if present
    original_transcript_data = None
    orig_path = ORIGINAL_TRANSCRIPTS_DIR / f"{story_id}.json"
    if orig_path.exists():
        try:
            with open(orig_path, "r", encoding="utf-8") as f:
                original_transcript_data = json.load(f)
        except Exception:
            original_transcript_data = None

    # Verify story was not concurrently modified or removed during export generation
    verify_row = conn.execute("SELECT transcript_revision FROM stories WHERE id = ?;", (story_id,)).fetchone()
    if not verify_row:
        raise ExportError("STORY_NOT_FOUND", f"Story '{story_id}' was removed during export generation.")
    if verify_row["transcript_revision"] != current_rev:
        raise ExportError("REVISION_CONFLICT", "Story transcript was modified during export generation.")

    # 6. Build Member Documents
    now_utc = datetime.now(timezone.utc).isoformat()

    # story.json
    story_json_data = {
        "id": story["id"],
        "title": story["title"],
        "speaker_label": story.get("speaker_label"),
        "consent_confirmed_at": story.get("consent_confirmed_at"),
        "audio_media_type": story.get("audio_media_type"),
        "audio_size_bytes": story.get("audio_size_bytes"),
        "audio_duration_ms": story.get("audio_duration_ms"),
        "transcript_revision": story.get("transcript_revision"),
        "transcript_reviewed_at": story.get("transcript_reviewed_at"),
        "created_at": story.get("created_at"),
        "updated_at": story.get("updated_at"),
    }
    story_json_bytes = json.dumps(story_json_data, indent=2, ensure_ascii=False).encode("utf-8")

    # transcript.json
    transcript_json_data = {
        "story_id": story_id,
        "transcript_revision": story.get("transcript_revision"),
        "transcript_reviewed_at": story.get("transcript_reviewed_at"),
        "segment_count": len(segments),
        "segments": segments,
        "original_machine_transcript": original_transcript_data,
    }
    transcript_json_bytes = json.dumps(transcript_json_data, indent=2, ensure_ascii=False).encode("utf-8")

    # memories.json
    memories_json_data = {
        "story_id": story_id,
        "current_transcript_revision": current_rev,
        "card_count": len(cards),
        "cards": cards,
    }
    memories_json_bytes = json.dumps(memories_json_data, indent=2, ensure_ascii=False).encode("utf-8")

    # story.html
    html_content = generate_offline_html(story, segments, cards, audio_member_name)
    html_bytes = html_content.encode("utf-8")

    # Files to include in ZIP and manifest
    file_payloads: List[Tuple[str, bytes]] = [
        (audio_member_name, audio_bytes),
        ("story.json", story_json_bytes),
        ("transcript.json", transcript_json_bytes),
        ("memories.json", memories_json_bytes),
        ("story.html", html_bytes),
    ]

    # manifest.json
    manifest_files = []
    for member_name, member_bytes in file_payloads:
        # Zip slip protection assertion
        if "/" in member_name or "\\" in member_name or ".." in member_name:
            raise ExportError("SECURITY_ERROR", f"Unsafe archive member name: {member_name}")
        manifest_files.append({
            "path": member_name,
            "size_bytes": len(member_bytes),
            "sha256": _sha256_bytes(member_bytes),
        })

    manifest_data = {
        "format": "echoarchive-export-v1",
        "exported_at": now_utc,
        "application": "EchoArchive",
        "version": "0.1.0",
        "story_id": story_id,
        "files": manifest_files,
    }
    manifest_bytes = json.dumps(manifest_data, indent=2, ensure_ascii=False).encode("utf-8")
    file_payloads.append(("manifest.json", manifest_bytes))

    # Assemble ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for member_name, member_bytes in file_payloads:
            # Re-verify path safety
            if "/" in member_name or "\\" in member_name or ".." in member_name:
                raise ExportError("SECURITY_ERROR", f"Unsafe archive member name: {member_name}")
            zf.writestr(member_name, member_bytes)

    # Verify zip integrity
    zip_buffer.seek(0)
    with zipfile.ZipFile(zip_buffer, mode="r") as test_zf:
        bad_file = test_zf.testzip()
        if bad_file:
            raise ExportError("CORRUPT_ARCHIVE", f"Archive CRC check failed for: {bad_file}")
        namelist = test_zf.namelist()
        if "manifest.json" not in namelist or "story.html" not in namelist:
            raise ExportError("INCOMPLETE_ARCHIVE", "Generated export is missing required archive members.")

    zip_buffer.seek(0)
    return zip_buffer
