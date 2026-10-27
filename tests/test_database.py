"""Deterministic unit tests for SQLite database schema and foreign keys."""

import sqlite3
from pathlib import Path

import pytest

from backend.database import get_db, init_db


@pytest.fixture
def test_db(tmp_path: Path):
    """Fixture creating an isolated test SQLite database."""
    db_file = tmp_path / "test_echoarchive.sqlite3"
    init_db(db_file)
    return db_file


def test_schema_tables_exist(test_db: Path):
    """Test that all required schema tables are created."""
    expected_tables = {
        "stories",
        "transcript_segments",
        "memory_cards",
        "memory_sources",
        "jobs",
    }
    with get_db(test_db) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert expected_tables.issubset(tables)


def test_foreign_key_enforcement(test_db: Path):
    """Test that SQLite strictly enforces foreign key constraints."""
    with get_db(test_db) as conn:
        # Attempt to insert a transcript segment pointing to nonexistent story
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text)
                VALUES ('seg-1', 'nonexistent-story-uuid', 0, 0, 1000, 'Orphaned segment');
                """
            )


def test_cascade_deletion(test_db: Path):
    """Test that deleting a story cascades and deletes all related segments, cards, and jobs."""
    story_id = "story-1234"
    card_id = "card-5678"
    seg_id = "seg-9999"

    with get_db(test_db) as conn:
        # Insert story
        conn.execute(
            """
            INSERT INTO stories (
                id, title, consent_confirmed_at, audio_relpath, audio_media_type, audio_size_bytes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (story_id, "Test Story", "2026-10-28T00:00:00Z", "audio/1234.wav", "audio/wav", 1024, "2026-10-28T00:00:00Z", "2026-10-28T00:00:00Z")
        )
        # Insert segment
        conn.execute(
            """
            INSERT INTO transcript_segments (id, story_id, segment_index, start_ms, end_ms, text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (seg_id, story_id, 0, 0, 2000, "Spoken words.")
        )
        # Insert card
        conn.execute(
            """
            INSERT INTO memory_cards (id, story_id, title, summary, generated_from_revision, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (card_id, story_id, "Memory Title", "Summary text.", 1, "2026-10-28T00:00:00Z")
        )
        # Insert source link
        conn.execute(
            """
            INSERT INTO memory_sources (card_id, segment_id)
            VALUES (?, ?)
            """,
            (card_id, seg_id)
        )

        # Confirm rows exist
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?", (story_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM memory_sources WHERE card_id = ?", (card_id,)).fetchone()[0] == 1

        # Delete story
        conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))

        # Verify cascades
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?", (story_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_sources WHERE card_id = ?", (card_id,)).fetchone()[0] == 0
