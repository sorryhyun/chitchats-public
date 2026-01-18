"""
CRUD operations for Room entities.
"""

import logging
from datetime import datetime
from typing import List, Optional

import schemas
from infrastructure.database import Agent, Room
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from .helpers import get_room_with_relationships

logger = logging.getLogger("CRUD")


async def create_room(db: AsyncSession, room: schemas.RoomCreate, owner_id: str) -> Room:
    """Create a new room scoped to a specific owner. Provider is immutable after creation."""
    db_room = Room(
        name=room.name,
        max_interactions=room.max_interactions,
        owner_id=owner_id,
        default_provider=room.default_provider or "claude",
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
    query = select(Room).order_by(Room.last_activity_at.desc())

    # Guests only see their own rooms
    if identity and getattr(identity, "role", None) != "admin":
        query = query.where(Room.owner_id == getattr(identity, "user_id", None))

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
            is_finished=bool(room.is_finished),
            default_provider=room.default_provider or "claude",
            created_at=room.created_at,
            last_activity_at=room.last_activity_at,
            last_read_at=room.last_read_at,
            has_unread=has_unread,
        )
        room_summaries.append(room_summary)

    # Sort: unread rooms first, then by last_activity_at descending
    room_summaries.sort(key=lambda r: (not r.has_unread, -(r.last_activity_at or r.created_at).timestamp()))

    return room_summaries


async def get_room(db: AsyncSession, room_id: int) -> Optional[Room]:
    """Get a specific room with all relationships."""
    return await get_room_with_relationships(db, room_id)


async def update_room(db: AsyncSession, room_id: int, room_update: schemas.RoomUpdate) -> Optional[Room]:
    """Update room configuration (max_interactions, is_paused)."""
    room = await get_room_with_relationships(db, room_id)

    if not room:
        return None

    # Update fields if provided
    if room_update.max_interactions is not None:
        # Validate max_interactions is non-negative
        if room_update.max_interactions < 0:
            raise ValueError("max_interactions must be non-negative")
        room.max_interactions = room_update.max_interactions
    if room_update.is_paused is not None:
        room.is_paused = room_update.is_paused

    await db.commit()
    await db.refresh(room, attribute_names=["agents", "messages"])

    # Invalidate room cache
    from infrastructure.cache import get_cache, room_object_key

    cache = get_cache()
    cache.invalidate(room_object_key(room_id))

    return room


async def mark_room_as_read(db: AsyncSession, room_id: int) -> Optional[Room]:
    """
    Mark a room as read by updating last_read_at to current time.
    This is used to track which rooms have unread messages.
    """
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()

    if not room:
        return None

    room.last_read_at = datetime.utcnow()
    await db.commit()
    await db.refresh(room)
    return room


async def delete_room(db: AsyncSession, room_id: int) -> bool:
    """Delete a room permanently."""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if room:
        await db.delete(room)
        await db.commit()
        return True
    return False


async def get_or_create_direct_room(db: AsyncSession, agent_id: int, owner_id: str) -> Optional[Room]:
    """Get or create a direct 1-on-1 room with an agent."""
    # First, check if agent exists
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    if not agent:
        return None

    # Look for existing direct room with this agent for the current owner
    # Direct rooms have naming convention: "Direct: {agent_name}"
    room_name = f"Direct: {agent.name}"

    result = await db.execute(
        select(Room)
        .options(selectinload(Room.agents), selectinload(Room.messages))
        .where(Room.name == room_name)
        .where(Room.owner_id == owner_id)
    )
    room = result.scalar_one_or_none()

    # If room exists, return it
    if room:
        return room

    # Otherwise, create a new direct room (default to claude provider)
    db_room = Room(name=room_name, owner_id=owner_id, default_provider="claude")
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
