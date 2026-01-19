"""
Cached CRUD operations for performance optimization.

This module provides cached versions of frequently called CRUD operations
to reduce database load, especially for polling endpoints.

Caching strategy:
- Agents: 5 minute TTL (rarely change)
- Rooms: 30 second TTL (max_interactions, is_paused may change)
- Room agents: 1 minute TTL (agents added/removed occasionally)
- Messages: 5 second TTL (high write frequency, need fresh data)
"""

import logging
from typing import List, Optional

from infrastructure.cache import agent_object_key, get_cache, room_agents_key, room_messages_key, room_object_key
from infrastructure.database import models
from sqlalchemy.ext.asyncio import AsyncSession

import crud

logger = logging.getLogger("CachedCRUD")


async def get_agent_cached(db: AsyncSession, agent_id: int) -> Optional[models.Agent]:
    """
    Get agent with caching (TTL: 5 minutes).

    Args:
        db: Database session
        agent_id: Agent ID

    Returns:
        Agent object or None
    """
    cache = get_cache()
    key = agent_object_key(agent_id)

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_agent(db, agent_id),
        ttl_seconds=300,  # 5 minutes
    )


async def get_room_cached(db: AsyncSession, room_id: int) -> Optional[models.Room]:
    """
    Get room with caching (TTL: 30 seconds).

    Args:
        db: Database session
        room_id: Room ID

    Returns:
        Room object or None
    """
    cache = get_cache()
    key = room_object_key(room_id)

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_room(db, room_id),
        ttl_seconds=30,  # 30 seconds
    )


async def get_agents_cached(db: AsyncSession, room_id: int) -> List[models.Agent]:
    """
    Get agents in a room with caching (TTL: 1 minute).

    Args:
        db: Database session
        room_id: Room ID

    Returns:
        List of agents in the room
    """
    cache = get_cache()
    key = room_agents_key(room_id)

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_agents(db, room_id),
        ttl_seconds=60,  # 1 minute
    )


async def get_messages_cached(db: AsyncSession, room_id: int) -> List[models.Message]:
    """
    Get messages in a room with caching (TTL: 5 seconds).

    Note: Short TTL because messages are written frequently.
    For polling, use get_messages_since which doesn't need caching.

    Args:
        db: Database session
        room_id: Room ID

    Returns:
        List of all messages in the room
    """
    cache = get_cache()
    key = room_messages_key(room_id)

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_messages(db, room_id),
        ttl_seconds=5,  # 5 seconds
    )


async def get_recent_messages_cached(db: AsyncSession, room_id: int, limit: int = 200) -> List[models.Message]:
    """Get recent messages with caching to avoid repeated DB hits."""
    cache = get_cache()
    key = f"{room_messages_key(room_id)}:recent:{limit}"

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_recent_messages(db, room_id, limit),
        ttl_seconds=5,
    )


async def get_messages_since_cached(
    db: AsyncSession,
    room_id: int,
    since_id: int | None = None,
    limit: int = 100,
) -> List[models.Message]:
    """
    Get new messages since a specific ID using a cached recent slice.

    This avoids a fresh database query on every poll while keeping the
    result bounded.
    """
    # Use a buffer to reduce cache misses when since_id increments rapidly
    buffered_limit = max(limit * 2, 50)
    recent_messages = await get_recent_messages_cached(db, room_id, buffered_limit)

    if since_id is None:
        return recent_messages[:limit]

    filtered = [m for m in recent_messages if m.id > since_id]
    return filtered[:limit]


async def get_messages_after_agent_response_cached(
    db: AsyncSession,
    room_id: int,
    agent_id: int,
    limit: int = 200,
) -> List[models.Message]:
    """Get messages after an agent's last response, cached briefly."""
    cache = get_cache()
    key = f"{room_messages_key(room_id)}:after:{agent_id}:{limit}"

    return await cache.get_or_set_async(
        key=key,
        factory=lambda: crud.get_messages_after_agent_response(db, room_id, agent_id, limit),
        ttl_seconds=5,
    )


# Cache invalidation helpers


def invalidate_room_cache(room_id: int):
    """
    Invalidate all cache entries related to a room.

    Args:
        room_id: Room ID
    """
    cache = get_cache()
    cache.invalidate(room_object_key(room_id))
    cache.invalidate(room_agents_key(room_id))
    # Invalidate all message-related entries (full list + recent slices)
    cache.invalidate_pattern(room_messages_key(room_id))
    logger.debug(f"Invalidated cache for room {room_id}")


def invalidate_agent_cache(agent_id: int):
    """
    Invalidate all cache entries related to an agent.

    Args:
        agent_id: Agent ID
    """
    from infrastructure.cache import agent_config_key

    cache = get_cache()
    cache.invalidate(agent_object_key(agent_id))
    cache.invalidate(agent_config_key(agent_id))
    logger.debug(f"Invalidated cache for agent {agent_id}")


def invalidate_messages_cache(room_id: int):
    """
    Invalidate message cache for a room.

    Args:
        room_id: Room ID
    """
    cache = get_cache()
    cache.invalidate_pattern(room_messages_key(room_id))
    logger.debug(f"Invalidated message cache for room {room_id}")
