"""User account management routes."""

import crud
from chatroom_orchestration import ChatOrchestrator
from core import (
    RequestIdentity,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
)
from core.agent_service import clear_room_messages_with_cleanup
from core.manager import AgentManager
from infrastructure.database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.delete("/conversations")
async def reset_all_conversations(
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    agent_manager: AgentManager = Depends(get_agent_manager),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """
    Reset all conversation history for the current user.

    This clears all messages from all rooms owned by the current user,
    while keeping the rooms and agents intact.
    """
    # Get all rooms for the current user
    rooms = await crud.get_rooms(db, identity)

    cleared_count = 0
    for room in rooms:
        success = await clear_room_messages_with_cleanup(
            db, room.id, agent_manager, chat_orchestrator
        )
        if success:
            cleared_count += 1

    return {
        "message": f"Cleared conversations from {cleared_count} rooms",
        "rooms_cleared": cleared_count,
    }
