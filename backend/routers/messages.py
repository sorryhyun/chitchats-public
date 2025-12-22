"""Message-related routes for polling, sending, and listing messages."""

import asyncio
import logging
from typing import List

import crud
import schemas
from database import get_db
from dependencies import (
    RequestIdentity,
    ensure_room_access,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
)
from exceptions import RoomNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Request
from infrastructure.images import compress_image_base64
from orchestration import ChatOrchestrator
from sdk import AgentManager
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger("MessageRouter")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


@router.get("/{room_id}/messages", response_model=List[schemas.Message])
async def list_messages(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """List all messages in a room."""
    await ensure_room_access(db, room_id, identity)
    # Use uncached query to avoid serving stale or empty caches on hard reloads
    return await crud.get_messages(db, room_id)


@router.get("/{room_id}/messages/poll", response_model=List[schemas.Message])
@limiter.limit("60/minute")  # 60 requests per minute per IP
async def poll_messages(
    request: Request,
    room_id: int,
    since_id: int = None,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for new messages in a room since a specific message ID.
    Used by frontend for polling-based message updates.

    Args:
        room_id: Room ID
        since_id: Only return messages with ID greater than this (optional)

    Returns:
        List of new messages
    """
    await ensure_room_access(db, room_id, identity)
    return await crud.get_messages_since_cached(db, room_id, since_id)


@router.get("/{room_id}/chatting-agents")
@limiter.limit("120/minute")  # 120 requests per minute per IP (allows faster polling)
async def get_chatting_agents(
    request: Request,
    room_id: int,
    db: AsyncSession = Depends(get_db),
    identity: RequestIdentity = Depends(get_request_identity),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """
    Get list of agents currently generating responses in a room.
    Used by frontend to display 'chatting...' indicators.

    Args:
        room_id: Room ID

    Returns:
        Dict with list of chatting agents (id, name, profile_pic)
    """
    # Verify room exists (use cache for performance)
    room = await crud.get_room_cached(db, room_id)
    if room is None:
        raise RoomNotFoundError(room_id)

    if identity.role != "admin" and room.owner_id != identity.user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this room")

    # Get currently chatting agent IDs from orchestrator
    chatting_agent_ids = chat_orchestrator.get_chatting_agents(room_id, agent_manager)

    # Get current streaming state (thinking/response text) for chatting agents
    streaming_state = agent_manager.get_streaming_state_for_room(room_id)

    # Get agent details for chatting agents (use cache for performance)
    chatting_agents = []
    if chatting_agent_ids:
        all_agents = await crud.get_agents_cached(db, room_id)
        agent_map = {agent.id: agent for agent in all_agents}

        for agent_id in chatting_agent_ids:
            if agent_id in agent_map:
                agent = agent_map[agent_id]
                agent_state = streaming_state.get(agent_id, {})
                chatting_agents.append(
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "profile_pic": agent.profile_pic,
                        "thinking_text": agent_state.get("thinking_text", ""),
                        "response_text": agent_state.get("response_text", ""),
                    }
                )

    return {"chatting_agents": chatting_agents}


@router.post("/{room_id}/messages/send", response_model=schemas.Message)
@limiter.limit("30/minute")  # 30 message sends per minute per IP
async def send_message(
    request: Request,
    room_id: int,
    message: schemas.MessageCreate,
    db: AsyncSession = Depends(get_db),
    identity: RequestIdentity = Depends(get_request_identity),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """
    Send a message to a room and trigger agent responses.
    Used by frontend for polling-based chat.

    Args:
        room_id: Room ID
        message: Message content and metadata

    Returns:
        The saved user message
    """
    from database import get_db as get_db_generator

    logger.info(
        f"[send_message] Received message for room {room_id}: content='{message.content[:50]}...', participant_type={message.participant_type}"
    )

    # Ensure the caller owns this room (admins bypass)
    await ensure_room_access(db, room_id, identity)

    # Compress image if present
    if message.image_data and message.image_media_type:
        try:
            logger.info(f"[send_message] Compressing image for room {room_id}")
            compressed_data, compressed_media_type = compress_image_base64(message.image_data, message.image_media_type)
            # Calculate compression ratio for logging
            original_size = len(message.image_data)
            compressed_size = len(compressed_data)
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            logger.info(
                f"[send_message] Image compressed: {original_size} -> {compressed_size} bytes "
                f"({compression_ratio:.1f}% reduction)"
            )
            # Update message with compressed data
            message.image_data = compressed_data
            message.image_media_type = compressed_media_type
        except Exception as e:
            logger.warning(f"[send_message] Image compression failed, using original: {e}")
            # Continue with original image if compression fails

    # Save user message and update room activity atomically
    saved_message = await crud.create_message(db, room_id, message, update_room_activity=True)
    logger.info(f"[send_message] Message saved with ID: {saved_message.id}")

    # Trigger agent responses in background (non-blocking)
    async def trigger_agent_responses():
        """Background task to trigger agent responses with its own DB session"""
        async for task_db in get_db_generator():
            try:
                await chat_orchestrator.handle_user_message(
                    db=task_db,
                    room_id=room_id,
                    message_data={
                        "content": message.content,
                        "participant_type": message.participant_type,
                        "participant_name": message.participant_name,
                        "mentioned_agent_ids": message.mentioned_agent_ids,
                    },
                    _manager=None,  # No connection manager needed for polling
                    agent_manager=agent_manager,
                    saved_user_message_id=saved_message.id,  # Pass the message ID to prevent duplication
                )
            except Exception as e:
                logger.error(f"Error triggering agent responses: {e}")
                import traceback

                traceback.print_exc()
            finally:
                pass  # Session cleanup handled by generator
            break  # Only use first (and only) session

    asyncio.create_task(trigger_agent_responses())

    return saved_message


@router.get("/{room_id}/critic-messages", response_model=List[schemas.Message])
async def list_critic_messages(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Get messages from critic agents for prompt optimization feedback."""
    await ensure_room_access(db, room_id, identity)
    return await crud.get_critic_messages(db, room_id)
