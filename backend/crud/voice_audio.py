"""
CRUD operations for VoiceAudio entities.
"""

from typing import Optional

from infrastructure.database import models
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload


async def get_voice_audio_by_message_id(db: AsyncSession, message_id: int) -> Optional[models.VoiceAudio]:
    """
    Get voice audio record by message ID.

    Args:
        db: Database session
        message_id: Message ID

    Returns:
        VoiceAudio record or None if not found
    """
    result = await db.execute(select(models.VoiceAudio).where(models.VoiceAudio.message_id == message_id))
    return result.scalar_one_or_none()


async def create_voice_audio(
    db: AsyncSession,
    message_id: int,
    agent_id: Optional[int],
    file_path: str,
    duration_ms: Optional[int] = None,
) -> models.VoiceAudio:
    """
    Create a new voice audio record.

    Args:
        db: Database session
        message_id: Message ID this audio is for
        agent_id: Agent ID (optional)
        file_path: Path to the audio file relative to sounds/
        duration_ms: Duration in milliseconds (optional)

    Returns:
        Created VoiceAudio record
    """
    db_voice = models.VoiceAudio(
        message_id=message_id,
        agent_id=agent_id,
        file_path=file_path,
        duration_ms=duration_ms,
    )
    db.add(db_voice)
    await db.commit()
    await db.refresh(db_voice)
    return db_voice


async def delete_voice_audio(db: AsyncSession, message_id: int) -> bool:
    """
    Delete voice audio record by message ID.

    Args:
        db: Database session
        message_id: Message ID

    Returns:
        True if deleted, False if not found
    """
    # Check if exists first
    existing = await get_voice_audio_by_message_id(db, message_id)
    if not existing:
        return False
    await db.execute(delete(models.VoiceAudio).where(models.VoiceAudio.message_id == message_id))
    await db.commit()
    return True


async def get_message_by_id(db: AsyncSession, message_id: int) -> Optional[models.Message]:
    """
    Get a message by its ID with agent relationship loaded.

    Args:
        db: Database session
        message_id: Message ID

    Returns:
        Message or None if not found
    """
    result = await db.execute(
        select(models.Message).options(selectinload(models.Message.agent)).where(models.Message.id == message_id)
    )
    return result.scalar_one_or_none()


async def voice_audio_exists(db: AsyncSession, message_id: int) -> bool:
    """
    Check if voice audio exists for a message.

    Args:
        db: Database session
        message_id: Message ID

    Returns:
        True if audio exists, False otherwise
    """
    result = await db.execute(
        select(models.VoiceAudio.id).where(models.VoiceAudio.message_id == message_id).limit(1)
    )
    return result.scalar_one_or_none() is not None
