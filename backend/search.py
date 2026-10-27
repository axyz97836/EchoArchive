"""Local-first parameterized archive search for EchoArchive."""

import html
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


def escape_like(query: str) -> str:
    """Escape LIKE wildcard characters for SQLite queries with ESCAPE '\\'."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def extract_snippet(text: str, query: str, window: int = 50) -> str:
    """Extract a bounded snippet around the query match with ellipses."""
    if not text:
        return ""
    lower_text = text.lower()
    lower_query = query.lower()
    pos = lower_text.find(lower_query)
    if pos == -1:
        if len(text) <= window * 2:
            return text
        return text[: window * 2] + "…"

    start = max(0, pos - window)
    end = min(len(text), pos + len(query) + window)

    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def search_archive(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Search stories, transcript segments, and memory cards locally using parameterized SQL.
    Strictly local-only, escapes wildcards, bounds query and results.
    """
    clean_query = query.strip()
    if not clean_query:
        return {"query": "", "total": 0, "results": []}

    like_term = f"%{escape_like(clean_query)}%"
    results: List[Dict[str, Any]] = []

    # 1. Search Stories (by title and speaker_label)
    story_cursor = conn.execute(
        """
        SELECT id, title, speaker_label, created_at
        FROM stories
        WHERE title LIKE ? ESCAPE '\\'
           OR (speaker_label IS NOT NULL AND speaker_label LIKE ? ESCAPE '\\')
        ORDER BY created_at DESC;
        """,
        (like_term, like_term),
    )
    for row in story_cursor.fetchall():
        matched_in = "title" if clean_query.lower() in row["title"].lower() else "speaker"
        snippet_source = row["title"] if matched_in == "title" else (row["speaker_label"] or "")
        results.append({
            "result_type": "story",
            "story_id": row["id"],
            "story_title": row["title"],
            "speaker_label": row["speaker_label"],
            "match_field": matched_in,
            "snippet": extract_snippet(snippet_source, clean_query),
            "created_at": row["created_at"],
        })

    # 2. Search Transcript Segments (authoritative spoken evidence)
    seg_cursor = conn.execute(
        """
        SELECT ts.id AS segment_id, ts.story_id, ts.segment_index, ts.start_ms, ts.end_ms,
               ts.text, ts.user_edited, s.title AS story_title, s.speaker_label
        FROM transcript_segments ts
        JOIN stories s ON ts.story_id = s.id
        WHERE ts.text LIKE ? ESCAPE '\\'
        ORDER BY s.created_at DESC, ts.segment_index ASC;
        """,
        (like_term,),
    )
    for row in seg_cursor.fetchall():
        results.append({
            "result_type": "transcript",
            "story_id": row["story_id"],
            "story_title": row["story_title"],
            "speaker_label": row["speaker_label"],
            "segment_id": row["segment_id"],
            "segment_index": row["segment_index"],
            "start_ms": row["start_ms"],
            "end_ms": row["end_ms"],
            "start_seconds": round(row["start_ms"] / 1000.0, 3),
            "end_seconds": round(row["end_ms"] / 1000.0, 3),
            "text": row["text"],
            "user_edited": bool(row["user_edited"]),
            "snippet": extract_snippet(row["text"], clean_query),
            "audio_url": f"/api/stories/{row['story_id']}/audio",
        })

    # 3. Search Memory Cards (AI summary, title, themes)
    card_cursor = conn.execute(
        """
        SELECT mc.id AS card_id, mc.story_id, mc.title, mc.summary, mc.themes_json,
               mc.generated_from_revision, mc.review_state,
               s.title AS story_title, s.speaker_label, s.transcript_revision
        FROM memory_cards mc
        JOIN stories s ON mc.story_id = s.id
        WHERE mc.title LIKE ? ESCAPE '\\'
           OR mc.summary LIKE ? ESCAPE '\\'
           OR mc.themes_json LIKE ? ESCAPE '\\'
        ORDER BY mc.created_at DESC;
        """,
        (like_term, like_term, like_term),
    )
    for row in card_cursor.fetchall():
        themes: List[str] = []
        try:
            themes = json.loads(row["themes_json"])
        except Exception:
            themes = []

        is_stale = (row["generated_from_revision"] != row["transcript_revision"])

        matched_field = "title"
        snippet_src = row["title"]
        if clean_query.lower() in row["summary"].lower():
            matched_field = "summary"
            snippet_src = row["summary"]
        elif any(clean_query.lower() in t.lower() for t in themes):
            matched_field = "themes"
            snippet_src = ", ".join(themes)

        results.append({
            "result_type": "memory",
            "story_id": row["story_id"],
            "story_title": row["story_title"],
            "speaker_label": row["speaker_label"],
            "card_id": row["card_id"],
            "card_title": row["title"],
            "summary": row["summary"],
            "themes": themes,
            "is_stale": is_stale,
            "review_state": row["review_state"],
            "match_field": matched_field,
            "snippet": extract_snippet(snippet_src, clean_query),
        })

    total = len(results)
    paginated = results[offset : offset + limit]

    return {
        "query": clean_query,
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": paginated,
    }
