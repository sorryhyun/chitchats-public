"""Shared dependencies for FastAPI endpoints."""

from typing import TYPE_CHECKING, NamedTuple

import crud
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import RoomNotFoundError

if TYPE_CHECKING:
    from chatroom_orchestration import ChatOrchestrator

    from core.manager import AgentManager


class RequestIdentity(NamedTuple):
    role: str
    user_id: str


def get_request_identity(request: Request) -> RequestIdentity:
    """Return the authenticated user's role and unique id from the request state."""
    role = getattr(request.state, "user_role", "admin")
    user_id = getattr(request.state, "user_id", role)
    return RequestIdentity(role=role, user_id=user_id)


async def ensure_room_access(db: AsyncSession, room_id: int, identity: RequestIdentity):
    """Ensure the current user can access the given room or raise an HTTP error."""
    room = await crud.get_room(db, room_id)
    if room is None:
        raise RoomNotFoundError(room_id)

    if identity.role != "admin" and room.owner_id != identity.user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this room")

    return room


def get_agent_manager(request: Request) -> "AgentManager":
    """
    Dependency to get the agent manager instance from app state.

    The instance is created during application startup in the lifespan context.
    """
    return request.app.state.agent_manager


def get_chat_orchestrator(request: Request) -> "ChatOrchestrator":
    """
    Dependency to get the chat orchestrator instance from app state.

    The instance is created during application startup in the lifespan context.
    """
    return request.app.state.chat_orchestrator
