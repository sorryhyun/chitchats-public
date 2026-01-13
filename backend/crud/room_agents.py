"""
CRUD operations for Room-Agent relationships and sessions.
"""

from datetime import datetime
from typing import List, Optional

from infrastructure.database import Agent, Message, Room, RoomAgentSession, room_agents
from sqlalchemy import func, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload


async def get_agents(db: AsyncSession, room_id: int) -> List[Agent]:
    """Get all agents in a specific room."""
    # Query agents directly via join to avoid detached instance issues with cached objects
    result = await db.execute(
        select(Agent).join(room_agents).where(room_agents.c.room_id == room_id)
    )
    return list(result.scalars().all())


async def add_agent_to_room(db: AsyncSession, room_id: int, agent_id: int) -> Optional[Room]:
    """Add an existing agent to a room with invitation tracking."""
    # Load room with agents only (not messages - too expensive for large conversations)
    room_result = await db.execute(
        select(Room).options(selectinload(Room.agents)).where(Room.id == room_id)
    )
    room = room_result.scalar_one_or_none()

    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    if room and agent:
        if agent not in room.agents:
            # Efficient check for existing messages (O(1) instead of loading all)
            has_messages = (
                await db.scalar(
                    select(func.count()).select_from(Message).where(Message.room_id == room_id).limit(1)
                )
                > 0
            )

            # Insert into room_agents with joined_at timestamp
            joined_at = datetime.utcnow()
            await db.execute(insert(room_agents).values(room_id=room_id, agent_id=agent_id, joined_at=joined_at))
            await db.commit()

            # Only create system message if this is a mid-conversation addition
            if has_messages:
                from crud.messages import create_system_message

                await create_system_message(db, room_id, f"{agent.name} joined the chat")

            # Refresh room to get updated agents only
            await db.refresh(room, attribute_names=["agents"])

            # Invalidate room agents cache
            from infrastructure.cache import get_cache, room_agents_key

            cache = get_cache()
            cache.invalidate(room_agents_key(room_id))

        return room
    return None


async def remove_agent_from_room(db: AsyncSession, room_id: int, agent_id: int) -> bool:
    """Remove an agent from a room (agent still exists globally)."""
    room_result = await db.execute(
        select(Room).options(selectinload(Room.agents)).where(Room.id == room_id)
    )
    room = room_result.scalar_one_or_none()

    if room:
        agent_to_remove = None
        for agent in room.agents:
            if agent.id == agent_id:
                agent_to_remove = agent
                break

        if agent_to_remove:
            room.agents.remove(agent_to_remove)
            await db.commit()

            # Invalidate room agents cache
            from infrastructure.cache import get_cache, room_agents_key

            cache = get_cache()
            cache.invalidate(room_agents_key(room_id))

            return True
    return False


async def get_room_agent_session(
    db: AsyncSession, room_id: int, agent_id: int, provider: str = "claude"
) -> Optional[str]:
    """Get the session/thread ID for a specific agent in a specific room.

    Args:
        db: Database session
        room_id: Room ID
        agent_id: Agent ID
        provider: AI provider ('claude' or 'codex')

    Returns:
        Session ID for Claude, thread ID for Codex, or None if not found
    """
    result = await db.execute(
        select(RoomAgentSession).where(
            RoomAgentSession.room_id == room_id, RoomAgentSession.agent_id == agent_id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return None

    # Use the model's get_session_id method for provider-specific retrieval
    return session.get_session_id(provider)


async def update_room_agent_session(
    db: AsyncSession, room_id: int, agent_id: int, session_id: str, provider: str = "claude"
) -> RoomAgentSession:
    """Update or create a session/thread ID for a specific agent in a specific room.

    Args:
        db: Database session
        room_id: Room ID
        agent_id: Agent ID
        session_id: The session/thread ID to store
        provider: AI provider ('claude' or 'codex')

    Returns:
        Updated RoomAgentSession
    """
    result = await db.execute(
        select(RoomAgentSession).where(
            RoomAgentSession.room_id == room_id, RoomAgentSession.agent_id == agent_id
        )
    )
    session = result.scalar_one_or_none()

    if session:
        # Update existing session using provider-specific method
        session.set_session_id(session_id, provider)
        session.updated_at = datetime.utcnow()
    else:
        # Create new session
        session = RoomAgentSession(room_id=room_id, agent_id=agent_id)
        session.set_session_id(session_id, provider)
        db.add(session)

    await db.commit()
    await db.refresh(session)
    return session
