"""
Server-Sent Events (SSE) router for real-time streaming.

This module provides SSE endpoints for streaming room events to clients
in real-time, replacing the need for polling during active conversations.
"""

import json
import logging
from typing import Optional

import crud
from chatroom_orchestration import ChatOrchestrator
from core import RequestIdentity, ensure_room_access, get_agent_manager, get_chat_orchestrator, get_request_identity
from core.auth import generate_sse_ticket, validate_sse_ticket
from core.manager import AgentManager
from core.sse import EventBroadcaster, generate_sse_events
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from infrastructure.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger("SSERouter")

router = APIRouter()


def get_broadcaster(request: Request) -> EventBroadcaster:
    """Get the EventBroadcaster from app state.

    Args:
        request: FastAPI request

    Returns:
        EventBroadcaster instance

    Raises:
        HTTPException: If broadcaster is not configured
    """
    broadcaster = getattr(request.app.state, "event_broadcaster", None)
    if broadcaster is None:
        raise HTTPException(status_code=500, detail="Event broadcaster not configured")
    return broadcaster


@router.post("/{room_id}/sse-ticket")
async def create_sse_ticket(
    room_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Generate a short-lived ticket for SSE connection.

    This endpoint creates a 60-second ticket that can be used to authenticate
    SSE connections. Since EventSource doesn't support custom headers, this
    allows the main JWT to stay in headers while only a short-lived,
    room-specific ticket appears in URLs/logs.

    Args:
        room_id: Room ID to generate ticket for
        request: FastAPI request (must be authenticated via X-API-Key header)
        db: Database session

    Returns:
        dict with ticket and expiry info
    """
    # Verify the room exists and this user is allowed to read it
    await ensure_room_access(db, room_id, identity)

    # Generate short-lived ticket (60 seconds). Possession of the ticket is proof
    # that room access was checked here, at issue time.
    ticket = generate_sse_ticket(room_id, user_id=identity.user_id, expiration_seconds=60)

    return {
        "ticket": ticket,
        "expires_in": 60,
        "room_id": room_id,
    }


@router.get("/{room_id}/stream")
async def stream_room_events(
    room_id: int,
    request: Request,
    ticket: Optional[str] = Query(None, description="Short-lived SSE ticket"),
    db: AsyncSession = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """SSE endpoint for streaming room events in real-time.

    This endpoint streams the following events:
    - `stream_start` - Agent started generating
    - `content_delta` - New response text (incremental)
    - `thinking_delta` - New thinking text (incremental)
    - `stream_end` - Agent finished
    - `new_message` - Message saved to DB
    - `keepalive` - Periodic ping (every 30s)

    Authentication:
        First obtain a ticket via POST /{room_id}/sse-ticket, then pass it
        via the `ticket` query parameter. Tickets are short-lived (60s) and
        room-specific.

    Args:
        room_id: Room ID to subscribe to
        ticket: Short-lived SSE ticket (from POST /{room_id}/sse-ticket)
        request: FastAPI request
        db: Database session

    Returns:
        EventSourceResponse streaming room events
    """
    # The auth middleware skips this route (EventSource cannot send headers), so the
    # ticket is the ONLY credential here. It is room-scoped, expires in 60s, and is
    # issued by create_sse_ticket only after that endpoint verifies room ownership —
    # which is what keeps a guest from subscribing to someone else's room.
    #
    # Never authorize from request.state here: get_request_identity defaults an absent
    # role to "admin", and this route never populates it.
    if not ticket:
        raise HTTPException(
            status_code=401, detail="Authentication required. Obtain a ticket via POST /{room_id}/sse-ticket"
        )

    if not validate_sse_ticket(ticket, room_id):
        raise HTTPException(status_code=401, detail="Invalid or expired ticket")

    if not await crud.get_room(db, room_id):
        raise HTTPException(status_code=404, detail="Room not found")

    # Get broadcaster from app state
    broadcaster = get_broadcaster(request)

    # Subscribe to room events
    connection = await broadcaster.subscribe(room_id)

    logger.info(f"SSE connection opened for room {room_id} (client: {connection.client_id})")

    # Get current streaming state for agents already generating responses
    # This ensures new clients see ongoing streams (e.g., when switching back to a room)
    chatting_agent_ids = chat_orchestrator.get_chatting_agents(room_id, agent_manager)
    streaming_state = agent_manager.get_streaming_state_for_room(room_id)

    # Build initial stream_start events for agents currently streaming
    initial_events = []
    if chatting_agent_ids:
        all_agents = await crud.get_agents_cached(db, room_id)
        agent_map = {agent.id: agent for agent in all_agents}

        for agent_id in chatting_agent_ids:
            if agent_id in agent_map:
                agent = agent_map[agent_id]
                agent_state = streaming_state.get(agent_id, {})
                # Send stream_start with current state so client can catch up
                initial_events.append(
                    {
                        "type": "stream_start",
                        "agent_id": agent_id,
                        "agent_name": agent.name,
                        # Don't include profile_pic - frontend can look it up or use cached value
                        "thinking_text": agent_state.get("thinking_text", ""),
                        "response_text": agent_state.get("response_text", ""),
                    }
                )

    async def event_generator():
        """Generate SSE events for the client."""
        try:
            # Send initial events for agents already streaming (catch-up for new clients)
            for event in initial_events:
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event),
                }

            # Then stream real-time events
            async for event in generate_sse_events(connection, broadcaster):
                # Convert event to SSE format
                yield {
                    "event": event.get("type", "message"),
                    "data": json.dumps(event),
                }
        except Exception as e:
            logger.error(f"SSE event generator error: {e}")
            raise

    return EventSourceResponse(event_generator())
