"""FastAPI application for EchoArchive local-first backend."""

import json
import logging
import shutil
import sqlite3
import urllib.parse
import uuid

logger = logging.getLogger("echoarchive.api")
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import (
    ALLOWED_ORIGIN_HOSTS,
    DATA_DIR,
    FFMPEG_BIN_PATH,
    HOST,
    MEDIA_DIR,
    OLLAMA_BASE_URL,
    PORT,
    PROJECT_ROOT,
    QWEN_MODEL_NAME,
    WHISPER_CLI_PATH,
    WHISPER_MODEL_PATH,
    ensure_storage_directories,
)
from backend.database import get_db, init_db
from backend.evidence import EvidenceValidationError
from backend.extraction import (
    ExtractionError,
    check_ollama_available,
    check_qwen_model_available,
)
from backend.jobs import (
    JobActiveError,
    JobError,
    JobQueueFullError,
    StoryNotFoundError,
    global_worker,
    recover_interrupted_jobs,
)
from backend.media import (
    MediaValidationError,
    check_ffmpeg_available,
    stream_and_validate_upload,
)
from backend.transcription import (
    TranscriptionError,
    check_whisper_available,
    check_whisper_model_available,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager ensuring directory readiness, migrations, worker startup and recovery."""
    ensure_storage_directories()
    init_db()
    recover_interrupted_jobs()
    global_worker.start()
    yield
    global_worker.stop()


app = FastAPI(
    title="EchoArchive API",
    description="Local-first speech preservation and traceable memory archive.",
    version="0.1.0",
    docs_url=None,  # Disabled in production boundary to minimize attack surface
    redoc_url=None,
    lifespan=lifespan,
)


# Security middleware: enforce localhost Origin/Host boundary on state-changing requests
@app.middleware("http")
async def security_origin_middleware(request: Request, call_next):
    """Enforce loopback Host and Origin validation for state-changing requests."""
    if request.method in ("POST", "PATCH", "DELETE", "PUT"):
        # Validate Host header
        raw_host = request.headers.get("host", "").split(":")[0].lower()
        if raw_host and raw_host not in ALLOWED_ORIGIN_HOSTS:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "FORBIDDEN", "message": "Untrusted Host header."}},
            )

        # Validate Origin header if present
        origin = request.headers.get("origin")
        if origin:
            parsed = urllib.parse.urlparse(origin)
            origin_host = (parsed.hostname or "").lower()
            if origin_host not in ALLOWED_ORIGIN_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "Cross-origin state-changing requests from untrusted origins are prohibited.",
                        }
                    },
                )

    return await call_next(request)


# Standardized error handlers
@app.exception_handler(MediaValidationError)
async def media_validation_exception_handler(request: Request, exc: MediaValidationError):
    """Map media validation errors to appropriate HTTP status codes."""
    status_code = 422
    if exc.code == "AUDIO_TOO_LARGE":
        status_code = 413
    elif exc.code == "UNSUPPORTED_AUDIO":
        status_code = 415
    elif exc.code == "AUDIO_TOO_LONG" or exc.code == "CONSENT_REQUIRED":
        status_code = 422
    elif exc.code == "FFMPEG_UNAVAILABLE":
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(JobActiveError)
async def job_active_exception_handler(request: Request, exc: JobActiveError):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(JobQueueFullError)
async def job_queue_full_exception_handler(request: Request, exc: JobQueueFullError):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(StoryNotFoundError)
async def story_not_found_exception_handler(request: Request, exc: StoryNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(JobError)
async def job_error_exception_handler(request: Request, exc: JobError):
    status_code = 422
    if exc.code == "REVISION_CONFLICT":
        status_code = 409
    elif exc.code == "NO_TRANSCRIPT":
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(TranscriptionError)
async def transcription_exception_handler(request: Request, exc: TranscriptionError):
    status_code = 502
    if exc.code == "TRANSCRIBER_UNAVAILABLE":
        status_code = 503
    elif exc.code == "TRANSCRIBER_TIMEOUT":
        status_code = 504
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ExtractionError)
async def extraction_exception_handler(request: Request, exc: ExtractionError):
    status_code = 502
    if exc.code == "OLLAMA_UNAVAILABLE":
        status_code = 503
    elif exc.code == "OLLAMA_TIMEOUT":
        status_code = 504
    elif exc.code in ("INVALID_EVIDENCE", "UNSUPPORTED_QUOTE"):
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(EvidenceValidationError)
async def evidence_validation_exception_handler(request: Request, exc: EvidenceValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Sanitize FastAPI / Pydantic validation errors into standard format."""
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "INVALID_REQUEST", "message": "The request contains invalid or malformed data."}},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Normalize HTTPException into standard error shape."""
    code = "HTTP_ERROR"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 409:
        code = "CONFLICT"
    elif exc.status_code == 403:
        code = "FORBIDDEN"

    msg = exc.detail if isinstance(exc.detail, str) else "A request error occurred."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": msg}},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Sanitized global exception handler preventing leaking paths or traces."""
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred."}},
    )


# Health check endpoint
@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Report genuine readiness of all local dependencies."""
    whisper_ready = check_whisper_available()
    model_ready = check_whisper_model_available()
    ffmpeg_ready = check_ffmpeg_available()
    ollama_ready = check_ollama_available()
    qwen_ready = check_qwen_model_available() if ollama_ready else False

    db_ready = False
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
            db_ready = True
    except Exception:
        db_ready = False

    all_ready = whisper_ready and model_ready and ffmpeg_ready and ollama_ready and qwen_ready and db_ready

    return {
        "status": "ready" if all_ready else "degraded",
        "services": {
            "speech_recognition": {
                "ready": whisper_ready and model_ready,
                "engine": "whisper.cpp",
                "cli_available": whisper_ready,
                "cli_path": WHISPER_CLI_PATH,
                "model_available": model_ready,
                "model_path": str(WHISPER_MODEL_PATH),
            },
            "media_preprocessing": {
                "ready": ffmpeg_ready,
                "tool": "ffmpeg",
                "path": FFMPEG_BIN_PATH,
            },
            "language_model": {
                "ready": ollama_ready and qwen_ready,
                "provider": "ollama",
                "endpoint": OLLAMA_BASE_URL,
                "server_reachable": ollama_ready,
                "model": QWEN_MODEL_NAME,
                "model_downloaded": qwen_ready,
            },
            "database": {
                "ready": db_ready,
                "engine": "sqlite3",
                "foreign_keys": True,
            },
            "storage": {
                "ready": True,
                "local_only": True,
            },
        },
    }


# Audio Ingestion & Story Creation Endpoint
@app.post("/api/stories", status_code=201)
async def create_story(
    audio: UploadFile = File(...),
    title: str = Form(...),
    speaker_label: Optional[str] = Form(None),
    permission_confirmed: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """
    Ingest a new spoken story recording with explicit permission acknowledgment.
    Enforces size (25 MiB), duration (5 minutes), media decode, and server-generated private storage.
    """
    # 1. Verify consent assertion
    if not permission_confirmed or permission_confirmed.strip().lower() not in ("true", "1", "yes"):
        raise MediaValidationError(
            "CONSENT_REQUIRED",
            "Affirmative confirmation of recording or upload permission is required."
        )

    # 2. Validate story title
    trimmed_title = title.strip() if title else ""
    if not trimmed_title or len(trimmed_title) > 160:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_TITLE", "message": "Story title must be between 1 and 160 characters."}},
        )

    # 3. Stream and validate audio upload
    temp_path, size_bytes, duration_seconds, extension, media_type = await stream_and_validate_upload(audio)

    # 4. Generate story UUID and permanent storage path
    story_id = str(uuid.uuid4())
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    permanent_audio_path = MEDIA_DIR / f"{story_id}{extension}"
    audio_relpath = f"media/{story_id}{extension}"

    try:
        shutil.move(str(temp_path), str(permanent_audio_path))
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "STORAGE_ERROR", "message": "Failed to store media file."}},
        )

    # 5. Persist story metadata in SQLite
    now_utc = datetime.now(timezone.utc).isoformat()
    duration_ms = int(duration_seconds * 1000)
    cleaned_speaker = speaker_label.strip() if speaker_label else None

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO stories (
                    id, title, speaker_label, consent_confirmed_at, audio_relpath,
                    audio_media_type, audio_size_bytes, audio_duration_ms,
                    transcript_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                """,
                (
                    story_id,
                    trimmed_title,
                    cleaned_speaker,
                    now_utc,
                    audio_relpath,
                    media_type,
                    size_bytes,
                    duration_ms,
                    now_utc,
                    now_utc,
                ),
            )
    except Exception as e:
        logger.exception("Failed to insert story into database: %s", e)
        # Reconcile on database failure by deleting stored media file
        if permanent_audio_path.exists():
            permanent_audio_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "DATABASE_ERROR", "message": "Failed to save story metadata."}},
        )

    return {
        "id": story_id,
        "title": trimmed_title,
        "speaker_label": cleaned_speaker,
        "audio_size_bytes": size_bytes,
        "audio_duration_ms": duration_ms,
        "transcript_revision": 0,
        "created_at": now_utc,
    }


# Story Listing & Search Endpoint
@app.get("/api/stories")
async def list_stories(
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Retrieve preserved stories with optional query filtering and pagination."""
    with get_db() as conn:
        if q and q.strip():
            query_term = f"%{q.strip()}%"
            count_row = conn.execute(
                "SELECT COUNT(*) as total FROM stories WHERE title LIKE ? OR speaker_label LIKE ?;",
                (query_term, query_term),
            ).fetchone()
            total = count_row["total"] if count_row else 0

            rows = conn.execute(
                """
                SELECT id, title, speaker_label, consent_confirmed_at, audio_relpath,
                       audio_media_type, audio_size_bytes, audio_duration_ms,
                       transcript_revision, transcript_reviewed_at, created_at, updated_at
                FROM stories
                WHERE title LIKE ? OR speaker_label LIKE ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (query_term, query_term, limit, offset),
            ).fetchall()
        else:
            count_row = conn.execute("SELECT COUNT(*) as total FROM stories;").fetchone()
            total = count_row["total"] if count_row else 0

            rows = conn.execute(
                """
                SELECT id, title, speaker_label, consent_confirmed_at, audio_relpath,
                       audio_media_type, audio_size_bytes, audio_duration_ms,
                       transcript_revision, transcript_reviewed_at, created_at, updated_at
                FROM stories
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()

        story_list = []
        for row in rows:
            story_dict = dict(row)
            story_dict["is_reviewed"] = story_dict.get("transcript_reviewed_at") is not None
            cards_count = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?;", (story_dict["id"],)).fetchone()[0]
            story_dict["memory_cards_count"] = cards_count
            seg_count = conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?;", (story_dict["id"],)).fetchone()[0]
            story_dict["transcript_segments_count"] = seg_count

            # Fetch most recent job if one exists
            job_row = conn.execute(
                """
                SELECT id, kind, status, stage, error_code, error_message
                FROM jobs WHERE story_id = ? ORDER BY created_at DESC LIMIT 1;
                """,
                (story_dict["id"],)
            ).fetchone()
            story_dict["current_job"] = dict(job_row) if job_row else None
            story_list.append(story_dict)

        return {"stories": story_list, "total": total}


# Story Details Endpoint
@app.get("/api/stories/{id}")
async def get_story(id: str) -> Dict[str, Any]:
    """Retrieve metadata, revision, review state, and job status for a single story."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM stories WHERE id = ?;", (id,)).fetchone()
        if not row:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' was not found."}},
            )

        story_dict = dict(row)
        story_dict["is_reviewed"] = story_dict.get("transcript_reviewed_at") is not None
        cards_count = conn.execute("SELECT COUNT(*) FROM memory_cards WHERE story_id = ?;", (id,)).fetchone()[0]
        story_dict["memory_cards_count"] = cards_count
        seg_count = conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?;", (id,)).fetchone()[0]
        story_dict["transcript_segments_count"] = seg_count

        job_row = conn.execute(
            """
            SELECT id, kind, status, stage, error_code, error_message, created_at, started_at, finished_at
            FROM jobs WHERE story_id = ? ORDER BY created_at DESC LIMIT 1;
            """,
            (id,)
        ).fetchone()
        story_dict["current_job"] = dict(job_row) if job_row else None
        return story_dict


# Audio Streaming / Seekable Playback Endpoint
def _parse_range_header(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    """Parse HTTP Range header: 'bytes=start-end'."""
    if not range_header or not range_header.startswith("bytes="):
        return None
    range_val = range_header.replace("bytes=", "").strip()
    parts = range_val.split("-")
    if len(parts) != 2:
        return None
    start_str, end_str = parts
    try:
        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            start = max(0, file_size - int(end_str))
            end = file_size - 1
        else:
            return None
    except ValueError:
        return None

    if start < 0 or start >= file_size or end < start:
        return None
    end = min(end, file_size - 1)
    return start, end


@app.get("/api/stories/{id}/audio")
async def get_story_audio(id: str, request: Request):
    """
    Serve seekable original recording using bounded HTTP range requests.
    Prevents path traversal and verifies local file presence.
    """
    with get_db() as conn:
        story = conn.execute("SELECT audio_relpath, audio_media_type FROM stories WHERE id = ?;", (id,)).fetchone()
        if not story:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' not found."}},
            )

    audio_path = (DATA_DIR / story["audio_relpath"]).resolve()
    # Path traversal and boundary verification
    try:
        audio_path.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "FORBIDDEN", "message": "Access to path outside media directory is denied."}},
        )

    if not audio_path.exists() or not audio_path.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "AUDIO_NOT_FOUND", "message": "Original recording audio file not found on disk."}},
        )

    file_size = audio_path.stat().st_size
    media_type = story["audio_media_type"] or "audio/wav"
    range_header = request.headers.get("range")

    if range_header:
        parsed_range = _parse_range_header(range_header, file_size)
        if parsed_range is None:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        start, end = parsed_range
        chunk_len = end - start + 1
        with open(audio_path, "rb") as f:
            f.seek(start)
            content = f.read(chunk_len)

        return Response(
            content=content,
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_len),
                "Content-Type": media_type,
            },
        )

    return FileResponse(
        path=audio_path,
        media_type=media_type,
        headers={"Accept-Ranges": "bytes"},
    )


# Transcription Initiation Endpoint
@app.post("/api/stories/{id}/transcribe", status_code=202)
async def start_transcription(id: str) -> Dict[str, Any]:
    """Start or retry offline speech recognition for a preserved story."""
    job_info = global_worker.enqueue_transcription(id)
    return job_info


# Job Polling Endpoint
@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Retrieve current state and stage transitions for an inference job."""
    with get_db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?;", (job_id,)).fetchone()
        if not job:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found."}},
            )

        return {
            "id": job["id"],
            "job_id": job["id"],
            "story_id": job["story_id"],
            "kind": job["kind"],
            "status": job["status"],
            "stage": job["stage"],
            "error_code": job["error_code"],
            "error_message": job["error_message"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
        }


# Transcript Segments Retrieval Endpoint
@app.get("/api/stories/{id}/segments")
async def get_story_segments(id: str) -> Dict[str, Any]:
    """Retrieve chronological, timestamped transcript segments for a story."""
    with get_db() as conn:
        story = conn.execute("SELECT id, transcript_revision FROM stories WHERE id = ?;", (id,)).fetchone()
        if not story:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' not found."}},
            )

        cursor = conn.execute(
            """
            SELECT id, segment_index, start_ms, end_ms, text, user_edited
            FROM transcript_segments
            WHERE story_id = ?
            ORDER BY segment_index ASC;
            """,
            (id,)
        )
        segments = [dict(row) for row in cursor.fetchall()]

        return {
            "story_id": id,
            "transcript_revision": story["transcript_revision"],
            "segments": segments,
        }


# Transcript Correction Endpoint (PATCH)
class TranscriptCorrectionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    expected_revision: int = Field(..., ge=1)


@app.patch("/api/stories/{id}/segments/{segment_id}")
async def update_transcript_segment(
    id: str,
    segment_id: str,
    payload: TranscriptCorrectionRequest,
) -> Dict[str, Any]:
    """
    Update a transcript segment with human review corrections.
    Uses optimistic concurrency with expected_revision to prevent conflicting overwrites.
    """
    trimmed_text = payload.text.strip()
    if not trimmed_text:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_CORRECTION", "message": "Corrected segment text cannot be empty."}},
        )

    with get_db() as conn:
        # 1. Verify story exists
        story = conn.execute("SELECT id, transcript_revision FROM stories WHERE id = ?;", (id,)).fetchone()
        if not story:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' not found."}},
            )

        # 2. Verify segment exists and belongs to this story
        segment = conn.execute(
            "SELECT * FROM transcript_segments WHERE id = ?;",
            (segment_id,)
        ).fetchone()
        if not segment:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "SEGMENT_NOT_FOUND", "message": f"Segment '{segment_id}' not found."}},
            )

        if segment["story_id"] != id:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "SEGMENT_NOT_FOUND",
                        "message": f"Segment '{segment_id}' does not belong to story '{id}'.",
                    }
                },
            )

        # 3. Optimistic concurrency check
        current_revision = story["transcript_revision"]
        if payload.expected_revision != current_revision:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "REVISION_CONFLICT",
                        "message": f"Transcript revision mismatch. Expected {payload.expected_revision}, but current revision is {current_revision}.",
                    }
                },
            )

        # 4. Atomically update story revision with compare-and-swap condition
        now_utc = datetime.now(timezone.utc).isoformat()
        new_revision = current_revision + 1

        update_cursor = conn.execute(
            """
            UPDATE stories
            SET transcript_revision = ?, transcript_reviewed_at = ?, updated_at = ?
            WHERE id = ? AND transcript_revision = ?;
            """,
            (new_revision, now_utc, now_utc, id, payload.expected_revision),
        )
        if update_cursor.rowcount == 0:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "REVISION_CONFLICT",
                        "message": f"Transcript revision conflict for story '{id}'. Expected revision was modified by a concurrent update.",
                    }
                },
            )

        conn.execute(
            """
            UPDATE transcript_segments
            SET text = ?, user_edited = 1
            WHERE id = ?;
            """,
            (trimmed_text, segment_id),
        )

        return {
            "segment": {
                "id": segment_id,
                "story_id": id,
                "segment_index": segment["segment_index"],
                "start_ms": segment["start_ms"],
                "end_ms": segment["end_ms"],
                "text": trimmed_text,
                "user_edited": 1,
            },
            "transcript_revision": new_revision,
            "transcript_reviewed_at": now_utc,
        }


# Human Review Confirmation Endpoint
@app.post("/api/stories/{id}/review")
async def confirm_story_review(id: str) -> Dict[str, Any]:
    """
    Explicitly confirm that a story's transcript has been reviewed and approved by a human.
    Enforces that transcript segments must exist before review confirmation is accepted.
    """
    with get_db() as conn:
        story = conn.execute("SELECT * FROM stories WHERE id = ?;", (id,)).fetchone()
        if not story:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' not found."}},
            )

        seg_count = conn.execute("SELECT COUNT(*) FROM transcript_segments WHERE story_id = ?;", (id,)).fetchone()[0]
        if seg_count == 0:
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "NO_TRANSCRIPT", "message": "Cannot confirm review for a story without transcript segments."}},
            )

        now_utc = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE stories SET transcript_reviewed_at = ?, updated_at = ? WHERE id = ?;",
            (now_utc, now_utc, id),
        )

        row = conn.execute("SELECT * FROM stories WHERE id = ?;", (id,)).fetchone()
        story_dict = dict(row)
        story_dict["is_reviewed"] = True
        return story_dict


# Memory Extraction Initiation Endpoint
class ExtractMemoriesRequest(BaseModel):
    expected_revision: Optional[int] = Field(None, ge=1)


@app.post("/api/stories/{id}/extract", status_code=202)
async def start_memory_extraction(
    id: str,
    payload: Optional[ExtractMemoriesRequest] = None,
) -> Dict[str, Any]:
    """
    Start asynchronous grounded memory extraction using local Qwen2.5.
    Requires an eligible story with a completed transcript.
    """
    expected_rev = payload.expected_revision if payload else None
    job_info = global_worker.enqueue_extraction(id, expected_revision=expected_rev)
    return job_info


# Memory Cards Retrieval Endpoint
@app.get("/api/stories/{id}/cards")
async def get_story_memory_cards(id: str) -> Dict[str, Any]:
    """
    Retrieve source-grounded memory cards for a story with computed stale flags
    and verified supporting transcript segment passages and seek timestamps.
    """
    with get_db() as conn:
        story = conn.execute(
            "SELECT id, title, transcript_revision, audio_duration_ms FROM stories WHERE id = ?;",
            (id,)
        ).fetchone()
        if not story:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "STORY_NOT_FOUND", "message": f"Story '{id}' not found."}},
            )

        current_revision = story["transcript_revision"]
        audio_duration_ms = story["audio_duration_ms"] or 0

        # Fetch cards
        cards_cursor = conn.execute(
            """
            SELECT id, story_id, title, summary, themes_json,
                   generated_from_revision, review_state, model_provenance, created_at
            FROM memory_cards
            WHERE story_id = ?
            ORDER BY created_at ASC;
            """,
            (id,)
        )
        card_rows = cards_cursor.fetchall()

        cards = []
        for crow in card_rows:
            card_id = crow["id"]
            gen_rev = crow["generated_from_revision"]
            is_stale = (gen_rev != current_revision)
            stale_reason = (
                f"Transcript has been modified since generation (card revision {gen_rev} vs current revision {current_revision})."
                if is_stale else None
            )

            # Fetch sources for this card
            sources_cursor = conn.execute(
                """
                SELECT ts.id, ts.segment_index, ts.start_ms, ts.end_ms, ts.text, ts.user_edited
                FROM memory_sources ms
                JOIN transcript_segments ts ON ms.segment_id = ts.id
                WHERE ms.card_id = ? AND ts.story_id = ?
                ORDER BY ts.segment_index ASC;
                """,
                (card_id, id)
            )
            sources = []
            for srow in sources_cursor.fetchall():
                start_ms = srow["start_ms"]
                end_ms = srow["end_ms"]
                timing_reliable = (
                    start_ms >= 0
                    and end_ms > start_ms
                    and (audio_duration_ms == 0 or end_ms <= audio_duration_ms + 1000)
                )
                sources.append({
                    "segment_id": srow["id"],
                    "segment_index": srow["segment_index"],
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "start_seconds": round(start_ms / 1000.0, 3),
                    "end_seconds": round(end_ms / 1000.0, 3),
                    "duration_seconds": round((end_ms - start_ms) / 1000.0, 3),
                    "text": srow["text"],
                    "user_edited": bool(srow["user_edited"]),
                    "story_id": id,
                    "audio_url": f"/api/stories/{id}/audio",
                    "transcript_revision": current_revision,
                    "timing_reliable": timing_reliable,
                    "seek_fallback_message": None if timing_reliable else "Precise timestamp unavailable; please listen from the beginning of the recording.",
                })

            themes = []
            try:
                themes = json.loads(crow["themes_json"])
            except Exception:
                themes = []

            cards.append({
                "id": card_id,
                "story_id": id,
                "title": crow["title"],
                "summary": crow["summary"],
                "themes": themes,
                "generated_from_revision": gen_rev,
                "is_stale": is_stale,
                "stale_reason": stale_reason,
                "review_state": crow["review_state"],
                "model_provenance": crow["model_provenance"],
                "created_at": crow["created_at"],
                "sources": sources,
            })

        has_stale = any(c["is_stale"] for c in cards)
        review_status = "review_needed" if any(c["review_state"] == "draft" for c in cards) else "reviewed"

        return {
            "story_id": id,
            "current_transcript_revision": current_revision,
            "cards": cards,
            "total": len(cards),
            "has_stale_cards": has_stale,
            "review_status": review_status,
        }


# Single Memory Card Details Endpoint
@app.get("/api/cards/{id}")
async def get_card_details(id: str) -> Dict[str, Any]:
    """Retrieve details, evidence citations, and stale state for a single memory card."""
    with get_db() as conn:
        crow = conn.execute(
            """
            SELECT id, story_id, title, summary, themes_json,
                   generated_from_revision, review_state, model_provenance, created_at
            FROM memory_cards
            WHERE id = ?;
            """,
            (id,)
        ).fetchone()
        if not crow:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "CARD_NOT_FOUND", "message": f"Memory card '{id}' not found."}},
            )

        story_id = crow["story_id"]
        story = conn.execute(
            "SELECT id, transcript_revision, audio_duration_ms FROM stories WHERE id = ?;",
            (story_id,)
        ).fetchone()
        current_revision = story["transcript_revision"] if story else crow["generated_from_revision"]
        audio_duration_ms = story["audio_duration_ms"] if story else 0

        is_stale = (crow["generated_from_revision"] != current_revision)
        stale_reason = (
            f"Transcript has been modified since generation (card revision {crow['generated_from_revision']} vs current revision {current_revision})."
            if is_stale else None
        )

        sources_cursor = conn.execute(
            """
            SELECT ts.id, ts.segment_index, ts.start_ms, ts.end_ms, ts.text, ts.user_edited
            FROM memory_sources ms
            JOIN transcript_segments ts ON ms.segment_id = ts.id
            WHERE ms.card_id = ? AND ts.story_id = ?
            ORDER BY ts.segment_index ASC;
            """,
            (id, story_id)
        )
        sources = []
        for srow in sources_cursor.fetchall():
            start_ms = srow["start_ms"]
            end_ms = srow["end_ms"]
            timing_reliable = (
                start_ms >= 0
                and end_ms > start_ms
                and (audio_duration_ms == 0 or end_ms <= audio_duration_ms + 1000)
            )
            sources.append({
                "segment_id": srow["id"],
                "segment_index": srow["segment_index"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "start_seconds": round(start_ms / 1000.0, 3),
                "end_seconds": round(end_ms / 1000.0, 3),
                "duration_seconds": round((end_ms - start_ms) / 1000.0, 3),
                "text": srow["text"],
                "user_edited": bool(srow["user_edited"]),
                "story_id": story_id,
                "audio_url": f"/api/stories/{story_id}/audio",
                "transcript_revision": current_revision,
                "timing_reliable": timing_reliable,
                "seek_fallback_message": None if timing_reliable else "Precise timestamp unavailable; please listen from the beginning of the recording.",
            })

        themes = []
        try:
            themes = json.loads(crow["themes_json"])
        except Exception:
            themes = []

        return {
            "id": crow["id"],
            "story_id": story_id,
            "title": crow["title"],
            "summary": crow["summary"],
            "themes": themes,
            "generated_from_revision": crow["generated_from_revision"],
            "is_stale": is_stale,
            "stale_reason": stale_reason,
            "review_state": crow["review_state"],
            "model_provenance": crow["model_provenance"],
            "created_at": crow["created_at"],
            "sources": sources,
        }


# Memory Card Sources Endpoint
@app.get("/api/cards/{id}/sources")
async def get_card_sources(id: str) -> Dict[str, Any]:
    """Retrieve supporting transcript segments and audio seek metadata for a card."""
    card = await get_card_details(id)
    if isinstance(card, JSONResponse):
        return card
    return {
        "card_id": id,
        "story_id": card["story_id"],
        "sources": card["sources"],
    }


# Memory Card Review State Update Endpoint (PATCH)
class UpdateCardReviewRequest(BaseModel):
    review_state: str = Field(..., pattern="^(draft|accepted|dismissed)$")


@app.patch("/api/cards/{id}")
async def update_card_review_state(id: str, payload: UpdateCardReviewRequest) -> Dict[str, Any]:
    """
    Update human review state (draft, accepted, or dismissed) of a memory card.
    Enforces that evidence citations and model provenance cannot be tampered with.
    """
    with get_db() as conn:
        card = conn.execute("SELECT id FROM memory_cards WHERE id = ?;", (id,)).fetchone()
        if not card:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "CARD_NOT_FOUND", "message": f"Memory card '{id}' not found."}},
            )

        conn.execute(
            "UPDATE memory_cards SET review_state = ? WHERE id = ?;",
            (payload.review_state, id)
        )

    return await get_card_details(id)


# Minimal Functional Playback Demonstration Harness Endpoint
DEMO_HTML_PATH = PROJECT_ROOT / "static" / "phase_c_demo.html"


@app.get("/demo", response_class=FileResponse)
@app.get("/phase-c-demo", response_class=FileResponse)
async def get_phase_c_demo():
    """Serve the minimal functional playback demonstration harness."""
    if not DEMO_HTML_PATH.exists():
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "Demo harness file not found."}}
        )
    return FileResponse(path=DEMO_HTML_PATH, media_type="text/html")


# Primary EchoArchive Web Application Endpoints
STATIC_DIR = PROJECT_ROOT / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"


@app.get("/", response_class=FileResponse)
@app.get("/app", response_class=FileResponse)
async def get_index():
    """Serve the primary EchoArchive application."""
    if not INDEX_HTML_PATH.exists():
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": "EchoArchive frontend index not found."}}
        )
    return FileResponse(path=INDEX_HTML_PATH, media_type="text/html")


# Mount /static directory for styles, scripts, and media assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


