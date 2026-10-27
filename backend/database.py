"""SQLite database management and schema migrations for EchoArchive."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from backend.config import DATABASE_PATH, DATA_DIR

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
    speaker_label TEXT,
    consent_confirmed_at TEXT NOT NULL,
    audio_relpath TEXT NOT NULL UNIQUE,
    audio_media_type TEXT NOT NULL,
    audio_size_bytes INTEGER NOT NULL CHECK(audio_size_bytes > 0),
    audio_duration_ms INTEGER,
    transcript_revision INTEGER NOT NULL DEFAULT 0
        CHECK(transcript_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL CHECK(segment_index >= 0),
    start_ms INTEGER NOT NULL CHECK(start_ms >= 0),
    end_ms INTEGER NOT NULL CHECK(end_ms > start_ms),
    text TEXT NOT NULL CHECK(length(trim(text)) > 0),
    user_edited INTEGER NOT NULL DEFAULT 0 CHECK(user_edited IN (0,1)),
    UNIQUE (story_id, segment_index)
);

CREATE TABLE IF NOT EXISTS memory_cards (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
    summary TEXT NOT NULL CHECK(length(summary) BETWEEN 1 AND 2000),
    themes_json TEXT NOT NULL DEFAULT '[]',
    generated_from_revision INTEGER NOT NULL CHECK(generated_from_revision >= 1),
    review_state TEXT NOT NULL DEFAULT 'draft'
        CHECK(review_state IN ('draft','accepted','dismissed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_sources (
    card_id TEXT NOT NULL REFERENCES memory_cards(id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
    PRIMARY KEY (card_id, segment_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('transcribe','extract')),
    status TEXT NOT NULL CHECK(status IN
        ('queued','running','succeeded','failed')),
    stage TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_segments_story_order
    ON transcript_segments(story_id, segment_index);
CREATE INDEX IF NOT EXISTS ix_cards_story
    ON memory_cards(story_id);
CREATE INDEX IF NOT EXISTS ix_jobs_story
    ON jobs(story_id, created_at);
CREATE INDEX IF NOT EXISTS ix_stories_created
    ON stories(created_at DESC);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database schema with foreign keys enabled and track migrations."""
    target_path = db_path or DATABASE_PATH
    if target_path != Path(":memory:"):
        target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path), timeout=30.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        if str(target_path) != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
        conn.executescript(SCHEMA_DDL)

        # Record migration version 1
        now_utc = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?);",
            (now_utc,)
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional database connection with foreign keys enabled."""
    target_path = db_path or DATABASE_PATH
    if target_path != Path(":memory:") and str(target_path) != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if str(target_path) != ":memory:":
        conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

