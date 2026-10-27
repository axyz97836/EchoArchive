"""FastAPI application for EchoArchive local-first backend."""

import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.config import (
    FFMPEG_BIN_PATH,
    HOST,
    OLLAMA_BASE_URL,
    PORT,
    QWEN_MODEL_NAME,
    WHISPER_CLI_PATH,
    WHISPER_MODEL_PATH,
    ensure_storage_directories,
)
from backend.database import get_db, init_db
from backend.extraction import check_ollama_available, check_qwen_model_available
from backend.media import check_ffmpeg_available
from backend.transcription import check_whisper_available, check_whisper_model_available


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager ensuring directory and database readiness."""
    ensure_storage_directories()
    init_db()
    yield


app = FastAPI(
    title="EchoArchive API",
    description="Local-first speech preservation and traceable memory archive.",
    version="0.1.0",
    docs_url=None,  # Disabled in production boundary to minimize attack surface
    redoc_url=None,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Sanitized global exception handler to prevent leaking paths or traces."""
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred."}},
    )


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Report genuine readiness of all local dependencies."""
    whisper_ready = check_whisper_available()
    model_ready = check_whisper_model_available()
    ffmpeg_ready = check_ffmpeg_available()
    ollama_ready = check_ollama_available()
    qwen_ready = check_qwen_model_available() if ollama_ready else False

    # Check database connectivity
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
