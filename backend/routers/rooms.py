"""Room management routes for CRUD operations and pause/resume."""

from typing import List

import crud
import schemas
from core.auth import require_admin
from core.dependencies import (
    RequestIdentity,
    ensure_room_access,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
)
from core.exceptions import RoomAlreadyExistsError
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from orchestration import ChatOrchestrator
from core import AgentManager
from crud import clear_room_messages_with_cleanup, delete_room_with_cleanup
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=List[schemas.RoomSummary])
async def list_rooms(identity: RequestIdentity = Depends(get_request_identity), db: AsyncSession = Depends(get_db)):
    """List all chat rooms."""
    rooms = await crud.get_rooms(db, identity)
    return rooms


@router.post("", response_model=schemas.Room)
async def create_room(
    room: schemas.RoomCreate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat room."""
    try:
        owner_id = "admin" if identity.role == "admin" else identity.user_id
        return await crud.create_room(db, room, owner_id=owner_id)
    except Exception as e:
        error_message = str(e)
        if (
            "UNIQUE constraint failed: rooms.owner_id, rooms.name" in error_message
            or "UNIQUE constraint failed: rooms.name" in error_message
        ):
            raise RoomAlreadyExistsError(room.name)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{room_id}", response_model=schemas.Room)
async def get_room(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific room by ID."""
    return await ensure_room_access(db, room_id, identity)


@router.patch("/{room_id}", response_model=schemas.Room)
async def update_room(
    room_id: int,
    room_update: schemas.RoomUpdate,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Update room configuration (max_interactions, is_paused)."""
    await ensure_room_access(db, room_id, identity)
    room = await crud.update_room(db, room_id, room_update)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("/{room_id}/pause", response_model=schemas.Room)
async def pause_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    identity: RequestIdentity = Depends(get_request_identity),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """
    Pause agent interactions in a room and interrupt any active agent responses.
    """
    await ensure_room_access(db, room_id, identity)

    room_update = schemas.RoomUpdate(is_paused=True)
    room = await crud.update_room(db, room_id, room_update)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    # Interrupt any agents currently processing responses in this room
    # Pass db to save any partial responses that were in-progress
    await chat_orchestrator.interrupt_room_processing(room_id, agent_manager, db=db)

    return room


@router.post("/{room_id}/resume", response_model=schemas.Room)
async def resume_room(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Resume agent interactions in a room."""
    await ensure_room_access(db, room_id, identity)
    room_update = schemas.RoomUpdate(is_paused=False)
    room = await crud.update_room(db, room_id, room_update)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("/{room_id}/mark-read")
async def mark_room_read(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Mark a room as read by updating last_read_at timestamp."""
    await ensure_room_access(db, room_id, identity)
    room = await crud.mark_room_as_read(db, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"message": "Room marked as read", "last_read_at": room.last_read_at}


@router.delete("/{room_id}", dependencies=[Depends(require_admin)])
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """Delete a room and cleanup all associated agent clients. (Admin only)"""
    success = await delete_room_with_cleanup(db, room_id, agent_manager, chat_orchestrator)
    if not success:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"message": "Room deleted successfully"}


@router.delete("/{room_id}/messages", dependencies=[Depends(require_admin)])
async def clear_room_messages(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """Clear all messages from a room and reset agent sessions. (Admin only)"""
    success = await clear_room_messages_with_cleanup(db, room_id, agent_manager, chat_orchestrator)
    if not success:
        raise HTTPException(status_code=404, detail="Room not found or no messages to delete")

    return {"message": "All messages cleared successfully"}
