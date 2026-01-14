"""Routes for managing agent-room relationships."""

from typing import List

import crud
import schemas
from core.auth import require_admin
from core.dependencies import RequestIdentity, ensure_room_access, get_agent_manager, get_request_identity
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from core import AgentManager
from crud import remove_agent_from_room_with_cleanup
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/{room_id}/agents", response_model=List[schemas.Agent])
async def list_room_agents(
    room_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Get all agents in a specific room."""
    await ensure_room_access(db, room_id, identity)
    return await crud.get_agents(db, room_id)


@router.post("/{room_id}/agents/{agent_id}", response_model=schemas.RoomWithAgents)
async def add_agent_to_room(
    room_id: int,
    agent_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Add an existing agent to a room."""
    await ensure_room_access(db, room_id, identity)
    room = await crud.add_agent_to_room(db, room_id, agent_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room or Agent not found")
    return room


@router.delete("/{room_id}/agents/{agent_id}", dependencies=[Depends(require_admin)])
async def remove_agent_from_room(
    room_id: int,
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager),
):
    """Remove an agent from a room and cleanup the associated client. (Admin only)"""
    success = await remove_agent_from_room_with_cleanup(db, room_id, agent_id, agent_manager)
    if not success:
        raise HTTPException(status_code=404, detail="Room or Agent not found")
    return {"message": "Agent removed from room successfully"}
