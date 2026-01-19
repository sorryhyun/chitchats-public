"""
CRUD operations for Room entities.
"""

import logging
from datetime import datetime
from typing import List, Optional

import schemas
from infrastructure.database import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from .helpers import get_room_with_relationships

logger = logging.getLogger("CRUD")


GUEST_MAX_INTERACTIONS = 50


async def create_room(db: AsyncSession, room: schemas.RoomCreate, owner_id: str) -> models.Room:
    """Create a new room scoped to a specific owner.

    Args:
        db: Database session
        room: Room creation data including optional provider
        owner_id: Owner identifier (user_id or guest-xxx)

    Returns:
        Created Room object
    """
    room_name = room.name
    max_interactions = room.max_interactions
    provider = room.provider or "claude"

    # Validate provider
    if provider not in ("claude", "codex"):
        raise ValueError(f"Invalid provider: {provider}")

    # Apply guest restrictions
    if owner_id.startswith("guest-"):
        room_name = f"guest: {room.name}"
        # Force max_interactions limit for guests
        if max_interactions is None or max_interactions > GUEST_MAX_INTERACTIONS:
            max_interactions = GUEST_MAX_INTERACTIONS

    db_room = models.Room(
        name=room_name,
        max_interactions=max_interactions,
        owner_id=owner_id,
        default_provider=provider,
    )
    db.add(db_room)
    await db.commit()
    await db.refresh(db_room, attribute_names=["agents", "messages"])
    return db_room


async def get_rooms(db: AsyncSession, identity=None) -> List[schemas.RoomSummary]:
    """
    Get all rooms with unread status computed and sorted by recency.
    Rooms with unread messages appear first, sorted by last_activity_at descending.
    """
    query = select(models.Room).order_by(models.Room.last_activity_at.desc())

    # Guests only see their own rooms
    if identity and getattr(identity, "role", None) != "admin":
        query = query.where(models.Room.owner_id == getattr(identity, "user_id", None))

    result = await db.execute(query)
    rooms = result.scalars().all()

    # Convert to RoomSummary with has_unread computed
    room_summaries = []
    for room in rooms:
        # Compute has_unread: True if last_activity_at > last_read_at (or last_read_at is None)
        has_unread = False
        if room.last_activity_at:
            if room.last_read_at is None:
                # Never read, but has activity
                has_unread = True
            else:
                # Compare timestamps
                has_unread = room.last_activity_at > room.last_read_at

        # Debug logging
        if has_unread:
            logger.info(
                f"[get_rooms] Room {room.id} ({room.name}) has_unread=True | activity={room.last_activity_at} > read={room.last_read_at}"
            )

        # Create RoomSummary with computed has_unread field
        room_summary = schemas.RoomSummary(
            id=room.id,
            name=room.name,
            owner_id=room.owner_id,
            max_interactions=room.max_interactions,
            is_paused=bool(room.is_paused),
            created_at=room.created_at,
            last_activity_at=room.last_activity_at,
            last_read_at=room.last_read_at,
            has_unread=has_unread,
        )
        room_summaries.append(room_summary)

    # Sort: unread rooms first, then by last_activity_at descending
    room_summaries.sort(key=lambda r: (not r.has_unread, -(r.last_activity_at or r.created_at).timestamp()))

    return room_summaries


async def get_room(db: AsyncSession, room_id: int) -> Optional[models.Room]:
    """Get a specific room with all relationships."""
    return await get_room_with_relationships(db, room_id)


async def update_room(db: AsyncSession, room_id: int, room_update: schemas.RoomUpdate) -> Optional[models.Room]:
    """Update room configuration (max_interactions, is_paused)."""
    room = await get_room_with_relationships(db, room_id)

    if not room:
        return None

    is_guest = room.owner_id and room.owner_id.startswith("guest-")

    # Update fields if provided
    if room_update.max_interactions is not None:
        # Validate max_interactions is non-negative
        if room_update.max_interactions < 0:
            raise ValueError("max_interactions must be non-negative")
        # Enforce guest limit
        max_val = room_update.max_interactions
        if is_guest and max_val > GUEST_MAX_INTERACTIONS:
            max_val = GUEST_MAX_INTERACTIONS
        room.max_interactions = max_val
    if room_update.is_paused is not None:
        room.is_paused = room_update.is_paused

    await db.commit()
    await db.refresh(room, attribute_names=["agents", "messages"])

    # Invalidate room cache
    from infrastructure.cache import get_cache, room_object_key

    cache = get_cache()
    cache.invalidate(room_object_key(room_id))

    return room


async def mark_room_as_read(db: AsyncSession, room_id: int) -> Optional[models.Room]:
    """
    Mark a room as read by updating last_read_at to current time.
    This is used to track which rooms have unread messages.
    """
    result = await db.execute(select(models.Room).where(models.Room.id == room_id))
    room = result.scalar_one_or_none()

    if not room:
        return None

    room.last_read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(room)
    return room


async def mark_room_as_finished(db: AsyncSession, room_id: int) -> Optional[models.Room]:
    """
    Mark a room as finished (all agents have skipped, conversation ended).
    """
    result = await db.execute(select(models.Room).where(models.Room.id == room_id))
    room = result.scalar_one_or_none()

    if not room:
        return None

    room.is_finished = True
    await db.commit()
    await db.refresh(room)
    return room


async def delete_room(db: AsyncSession, room_id: int) -> bool:
    """Delete a room permanently."""
    result = await db.execute(select(models.Room).where(models.Room.id == room_id))
    room = result.scalar_one_or_none()
    if room:
        await db.delete(room)
        await db.commit()
        return True
    return False


async def get_or_create_direct_room(
    db: AsyncSession, agent_id: int, owner_id: str, provider: str = "claude"
) -> Optional[models.Room]:
    """Get or create a direct 1-on-1 room with an agent.

    Args:
        db: Database session
        agent_id: ID of the agent
        owner_id: Owner identifier (user_id or guest-xxx)
        provider: AI provider - "claude" or "codex"

    Returns:
        Room object or None if agent not found
    """
    # Validate provider
    if provider not in ("claude", "codex"):
        raise ValueError(f"Invalid provider: {provider}")

    # First, check if agent exists
    agent_result = await db.execute(select(models.Agent).where(models.Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    if not agent:
        return None

    # Look for existing direct room with this agent for the current owner
    # Direct rooms have naming convention: "Direct: {agent_name}" or "guest: Direct: {agent_name}"
    # With provider suffix for non-claude: "Direct: {agent_name} (codex)"
    is_guest = owner_id.startswith("guest-")
    provider_suffix = f" ({provider})" if provider != "claude" else ""
    base_room_name = f"Direct: {agent.name}{provider_suffix}"
    room_name = f"guest: {base_room_name}" if is_guest else base_room_name

    result = await db.execute(
        select(models.Room)
        .options(selectinload(models.Room.agents), selectinload(models.Room.messages))
        .where(models.Room.name == room_name)
        .where(models.Room.owner_id == owner_id)
    )
    room = result.scalar_one_or_none()

    # If room exists, return it
    if room:
        return room

    # Otherwise, create a new direct room
    max_interactions = GUEST_MAX_INTERACTIONS if is_guest else None
    db_room = models.Room(
        name=room_name,
        owner_id=owner_id,
        max_interactions=max_interactions,
        default_provider=provider,
    )
    db.add(db_room)
    await db.flush()  # Flush to get the room ID

    # Refresh to load the agents relationship
    await db.refresh(db_room, attribute_names=["agents"])

    # Add the agent to the room
    db_room.agents.append(agent)

    await db.commit()
    # Refresh with all necessary relationships for response serialization
    await db.refresh(db_room, attribute_names=["agents", "messages"])
    return db_room
