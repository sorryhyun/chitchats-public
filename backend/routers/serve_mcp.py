"""
Simplified MCP tools for easy LLM integration.

These endpoints provide a clean, semantic interface for chatting with agents.
Tool names are designed to be intuitive: chat, list_agents, get_conversation, etc.
"""

from typing import Optional

import crud
import schemas
from core import (
    RequestIdentity,
    ensure_room_access,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
    get_settings,
)
from core.manager import AgentManager
from fastapi import APIRouter, Depends, HTTPException
from infrastructure.database import get_db
from chatroom_orchestration import ChatOrchestrator
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/mcp-tools", tags=["MCP Tools"])


# ============ Schemas ============


class AgentInfo(BaseModel):
    """Simple agent info"""

    id: int
    name: str
    group: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat with an agent"""

    agent_name: str = Field(..., description="Name of the agent to chat with (e.g., '프리렌', 'Dr. Chen')")
    message: str = Field(..., description="Your message to the agent")


class ChatResponse(BaseModel):
    """Agent's response"""

    agent_name: str
    response: str
    thinking: Optional[str] = None
    room_id: int


class RoomRequest(BaseModel):
    """Create a room with multiple agents"""

    name: str = Field(..., description="Name for the chat room")
    agent_names: list[str] = Field(..., description="List of agent names to add to the room")


class RoomMessageRequest(BaseModel):
    """Send message to a room"""

    room_id: int = Field(..., description="Room ID")
    message: str = Field(..., description="Your message")


class ConversationMessage(BaseModel):
    """A message in conversation"""

    role: str
    sender: str
    content: str
    thinking: Optional[str] = None


# ============ Endpoints ============


@router.get("/agents", response_model=list[AgentInfo], summary="List all available agents")
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[AgentInfo]:
    """
    Get a list of all available agents you can chat with.

    Returns agent names and their groups (if any).
    """
    agents = await crud.get_all_agents(db)
    return [AgentInfo(id=a.id, name=a.name, group=a.group) for a in agents]


@router.post("/chat", response_model=ChatResponse, summary="Chat with an agent")
async def chat(
    request: ChatRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> ChatResponse:
    """
    Send a message to an agent and get their response.

    This automatically handles room creation - each agent has a dedicated
    "direct message" room for 1-on-1 conversations.

    Example:
        chat(agent_name="프리렌", message="안녕! 요즘 어떻게 지내?")
    """
    # Find agent by name
    agents = await crud.get_all_agents(db)
    agent = next((a for a in agents if a.name == request.agent_name), None)

    if not agent:
        # Try partial match
        agent = next((a for a in agents if request.agent_name.lower() in a.name.lower()), None)

    if not agent:
        available = [a.name for a in agents[:10]]
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_name}' not found. Available: {available}")

    owner_id = "admin" if identity.role == "admin" else identity.user_id
    # Get or create direct room for this agent
    room = await crud.get_or_create_direct_room(db, agent.id, owner_id=owner_id)

    # Ensure agent is in the room
    room_agents = await crud.get_agents(db, room.id)
    if agent.id not in [a.id for a in room_agents]:
        await crud.add_agent_to_room(db, room.id, agent.id)

    settings = get_settings()
    user_name = settings.user_name

    # Send message
    message_data = schemas.MessageCreate(
        content=request.message,
        role="user",
        participant_type="user",
        participant_name=user_name,
    )
    user_msg = await crud.create_message(db, room.id, message_data)

    # Get agent response
    responses = await chat_orchestrator.orchestrate_responses(
        db=db,
        room=room,
        trigger_message=user_msg,
        agent_manager=agent_manager,
        responding_agents=[agent],
    )

    if responses:
        resp = responses[0]
        return ChatResponse(
            agent_name=agent.name,
            response=resp.content,
            thinking=resp.thinking,
            room_id=room.id,
        )
    else:
        return ChatResponse(
            agent_name=agent.name,
            response="*stays silent*",
            room_id=room.id,
        )


@router.get("/conversation/{agent_name}", response_model=list[ConversationMessage], summary="Get conversation history")
async def get_conversation(
    agent_name: str,
    limit: int = 20,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationMessage]:
    """
    Get recent conversation history with an agent.

    Returns the last N messages from your direct chat with this agent.
    """
    # Find agent
    agents = await crud.get_all_agents(db)
    agent = next((a for a in agents if a.name == agent_name), None)
    if not agent:
        agent = next((a for a in agents if agent_name.lower() in a.name.lower()), None)

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    owner_id = "admin" if identity.role == "admin" else identity.user_id
    # Get direct room (use get_or_create to find existing)
    room = await crud.get_or_create_direct_room(db, agent.id, owner_id=owner_id)
    if not room:
        return []

    # Get messages
    messages = await crud.get_messages(db, room.id, limit=limit)

    return [
        ConversationMessage(
            role=m.role,
            sender=m.agent_name or m.participant_name or m.role,
            content=m.content,
            thinking=m.thinking,
        )
        for m in messages
    ]


@router.post("/room", summary="Create a chat room with multiple agents")
async def create_room(
    request: RoomRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a new chat room and add multiple agents to it.

    Use this for group conversations with multiple agents.

    Example:
        create_room(name="Book Club", agent_names=["프리렌", "페른"])
    """
    # Create room
    owner_id = "admin" if identity.role == "admin" else identity.user_id
    room = await crud.create_room(db, schemas.RoomCreate(name=request.name), owner_id=owner_id)

    # Find and add agents
    agents = await crud.get_all_agents(db)
    added = []
    not_found = []

    for name in request.agent_names:
        agent = next((a for a in agents if a.name == name), None)
        if not agent:
            agent = next((a for a in agents if name.lower() in a.name.lower()), None)

        if agent:
            await crud.add_agent_to_room(db, room.id, agent.id)
            added.append(agent.name)
        else:
            not_found.append(name)

    return {
        "room_id": room.id,
        "room_name": room.name,
        "agents_added": added,
        "agents_not_found": not_found,
    }


@router.post("/room/message", response_model=list[ChatResponse], summary="Send message to a room")
async def send_to_room(
    request: RoomMessageRequest,
    identity: RequestIdentity = Depends(get_request_identity),
    db: AsyncSession = Depends(get_db),
    chat_orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    agent_manager: AgentManager = Depends(get_agent_manager),
) -> list[ChatResponse]:
    """
    Send a message to a room and get responses from all agents.

    Use this for group conversations where multiple agents may respond.
    """
    room = await crud.get_room(db, request.room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {request.room_id} not found")
    await ensure_room_access(db, request.room_id, identity)

    settings = get_settings()
    user_name = settings.user_name

    # Send message
    message_data = schemas.MessageCreate(
        content=request.message,
        role="user",
        participant_type="user",
        participant_name=user_name,
    )
    user_msg = await crud.create_message(db, room.id, message_data)

    # Get responding agents
    room_agents = await crud.get_agents(db, room.id)

    # Get responses
    responses = await chat_orchestrator.orchestrate_responses(
        db=db,
        room=room,
        trigger_message=user_msg,
        agent_manager=agent_manager,
        responding_agents=room_agents,
    )

    return [
        ChatResponse(
            agent_name=r.agent_name or "Agent",
            response=r.content,
            thinking=r.thinking,
            room_id=room.id,
        )
        for r in responses
    ]
