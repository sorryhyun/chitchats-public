"""Voice audio generation routes for TTS functionality."""

import logging
import sys
from pathlib import Path
from typing import Optional

import crud
import httpx
from core import RequestIdentity, get_request_identity, get_settings
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from infrastructure.database import get_db
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger("VoiceRouter")


def _get_sounds_dir() -> Path:
    """Get the sounds directory for storing cached audio files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "sounds"
    else:
        return Path(__file__).parent.parent.parent / "sounds"


class VoiceStatusResponse(BaseModel):
    """Response for voice server status check."""

    enabled: bool
    server_available: bool
    server_url: str


class VoiceGenerateRequest(BaseModel):
    """Request to generate voice audio for a message."""

    message_id: int
    room_id: int


class VoiceGenerateResponse(BaseModel):
    """Response from voice generation."""

    status: str
    file_path: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class VoiceExistsResponse(BaseModel):
    """Response for checking if audio exists."""

    exists: bool
    file_path: Optional[str] = None


@router.get("/status", response_model=VoiceStatusResponse)
async def get_voice_status(
    identity: RequestIdentity = Depends(get_request_identity),
):
    """
    Check voice server availability.

    Returns:
        Voice server status including whether it's enabled and available
    """
    settings = get_settings()
    voice_url = settings.voice_server_url

    server_available = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{voice_url}/health")
            if response.status_code == 200:
                data = response.json()
                server_available = data.get("tts_ready", False)
    except Exception as e:
        logger.debug(f"Voice server health check failed: {e}")

    return VoiceStatusResponse(
        enabled=True,  # Voice feature is always enabled, server may not be available
        server_available=server_available,
        server_url=voice_url,
    )


@router.post("/generate", response_model=VoiceGenerateResponse)
async def generate_voice(
    request: VoiceGenerateRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate voice audio for a message.

    Args:
        request: Contains message_id and room_id

    Returns:
        Generation status and file path if successful
    """
    settings = get_settings()
    voice_url = settings.voice_server_url

    # Check if audio already exists
    existing = await crud.get_voice_audio_by_message_id(db, request.message_id)
    if existing:
        return VoiceGenerateResponse(
            status="exists",
            file_path=existing.file_path,
            duration_ms=existing.duration_ms,
        )

    # Get the message
    message = await crud.get_message_by_id(db, request.message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Only generate for assistant messages
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only generate voice for assistant messages")

    # Get agent config for voice file
    voice_file = None
    voice_text = None
    agent_id = None

    if message.agent:
        agent_id = message.agent.id
        config_data = message.agent.get_config_data()
        if config_data:
            voice_file = config_data.voice_file
            voice_text = config_data.voice_text

    # Prepare request to voice server
    generate_request = {
        "text": message.content,
    }
    if voice_file:
        generate_request["voice_file"] = voice_file
    if voice_text:
        generate_request["voice_text"] = voice_text

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # TTS can take a while
            response = await client.post(
                f"{voice_url}/generate",
                json=generate_request,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"Voice server error: {error_detail}")
                return VoiceGenerateResponse(
                    status="error",
                    error=f"Voice server error: {response.status_code}",
                )

            # Save the audio file
            sounds_dir = _get_sounds_dir()
            sounds_dir.mkdir(parents=True, exist_ok=True)

            file_name = f"msg_{request.message_id}.wav"
            file_path = sounds_dir / file_name

            with open(file_path, "wb") as f:
                f.write(response.content)

            # Get duration from response headers if available
            duration_ms = None
            if "X-Duration-Ms" in response.headers:
                try:
                    duration_ms = int(response.headers["X-Duration-Ms"])
                except ValueError:
                    pass

            # Save to database
            await crud.create_voice_audio(
                db=db,
                message_id=request.message_id,
                agent_id=agent_id,
                file_path=file_name,
                duration_ms=duration_ms,
            )

            return VoiceGenerateResponse(
                status="success",
                file_path=file_name,
                duration_ms=duration_ms,
            )

    except httpx.TimeoutException:
        logger.error("Voice server request timed out")
        return VoiceGenerateResponse(
            status="error",
            error="Voice generation timed out",
        )
    except httpx.ConnectError:
        logger.error("Could not connect to voice server")
        return VoiceGenerateResponse(
            status="error",
            error="Voice server not available",
        )
    except Exception as e:
        logger.error(f"Voice generation error: {e}")
        return VoiceGenerateResponse(
            status="error",
            error=str(e),
        )


@router.get("/audio/{message_id}")
async def get_voice_audio(
    message_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Get cached voice audio for a message.

    Args:
        message_id: Message ID

    Returns:
        Audio file (WAV)
    """
    voice_audio = await crud.get_voice_audio_by_message_id(db, message_id)
    if not voice_audio:
        raise HTTPException(status_code=404, detail="Audio not found")

    sounds_dir = _get_sounds_dir()
    file_path = sounds_dir / voice_audio.file_path

    if not file_path.exists():
        # Clean up stale database record
        await crud.delete_voice_audio(db, message_id)
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        file_path,
        media_type="audio/wav",
        filename=voice_audio.file_path,
    )


@router.get("/exists/{message_id}", response_model=VoiceExistsResponse)
async def check_voice_exists(
    message_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if voice audio exists for a message.

    Args:
        message_id: Message ID

    Returns:
        Whether audio exists and its file path
    """
    voice_audio = await crud.get_voice_audio_by_message_id(db, message_id)
    if voice_audio:
        # Verify file actually exists
        sounds_dir = _get_sounds_dir()
        file_path = sounds_dir / voice_audio.file_path
        if file_path.exists():
            return VoiceExistsResponse(exists=True, file_path=voice_audio.file_path)
        else:
            # Clean up stale database record
            await crud.delete_voice_audio(db, message_id)

    return VoiceExistsResponse(exists=False)
