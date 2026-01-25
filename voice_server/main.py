"""
Voice server for TTS generation using Qwen3-TTS.

This server provides REST endpoints for text-to-speech synthesis
with optional voice cloning capabilities.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from tts_service import get_tts_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("VoiceServer")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    tts_ready: bool


class GenerateRequest(BaseModel):
    """Request to generate speech."""

    text: str
    voice_file: Optional[str] = None
    voice_text: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Starting voice server...")

    # Initialize TTS service
    try:
        tts = await get_tts_service()
        if tts.is_ready:
            logger.info("TTS service initialized successfully")
        else:
            logger.warning("TTS service not ready - model may not be loaded")
    except Exception as e:
        logger.error(f"Failed to initialize TTS service: {e}")
        # Continue anyway - health check will report not ready

    logger.info("Voice server started on port 8002")

    yield

    logger.info("Shutting down voice server...")


app = FastAPI(
    title="ChitChats Voice Server",
    description="TTS server using Qwen3-TTS",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Voice server is local-only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check server health and TTS readiness.

    Returns:
        Health status including whether TTS is ready
    """
    try:
        tts = await get_tts_service()
        return HealthResponse(status="ok", tts_ready=tts.is_ready)
    except Exception:
        return HealthResponse(status="ok", tts_ready=False)


@app.post("/generate")
async def generate_speech(request: GenerateRequest):
    """
    Generate speech audio from text.

    Args:
        request: Contains text and optional voice reference

    Returns:
        WAV audio file with duration header
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    try:
        tts = await get_tts_service()

        if not tts.is_ready:
            raise HTTPException(status_code=503, detail="TTS service not ready")

        wav_bytes, duration_ms = await tts.generate(
            text=request.text,
            voice_file=request.voice_file,
            voice_text=request.voice_text,
        )

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"X-Duration-Ms": str(duration_ms)},
        )

    except RuntimeError as e:
        logger.error(f"TTS generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during TTS generation: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
    )
