"""Agent CRUD routes and direct room access."""

from typing import List

import crud
import schemas
from auth import require_admin
from database import get_db
from dependencies import RequestIdentity, get_agent_manager, get_request_identity
from fastapi import APIRouter, Depends, HTTPException
from sdk import AgentManager
from services.agent_service import delete_agent_with_cleanup
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("", response_model=schemas.Agent, dependencies=[Depends(require_admin)])
async def create_agent(agent: schemas.AgentCreate, db: AsyncSession = Depends(get_db)):
    """Create a new agent as an independent entity. (Admin only)"""
    return await crud.create_agent(db, agent)


@router.get("", response_model=List[schemas.Agent])
async def list_all_agents(db: AsyncSession = Depends(get_db)):
    """Get all agents globally."""
    return await crud.get_all_agents(db)


@router.get("/{agent_id}", response_model=schemas.Agent)
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific agent."""
    agent = await crud.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", dependencies=[Depends(require_admin)])
async def delete_agent(
    agent_id: int, db: AsyncSession = Depends(get_db), agent_manager: AgentManager = Depends(get_agent_manager)
):
    """Delete an agent permanently and cleanup all associated clients. (Admin only)"""
    success = await delete_agent_with_cleanup(db, agent_id, agent_manager)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"message": "Agent deleted successfully"}


@router.get("/{agent_id}/direct-room", response_model=schemas.Room)
async def get_agent_direct_room(
    agent_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
):
    """Get or create a direct 1-on-1 room with an agent."""
    owner_id = "admin" if identity.role == "admin" else identity.user_id
    room = await crud.get_or_create_direct_room(db, agent_id, owner_id=owner_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if identity.role != "admin" and room.owner_id != identity.user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this room")
    return room
