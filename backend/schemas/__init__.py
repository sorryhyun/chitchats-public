"""
Pydantic schemas for API request/response models.

This package organizes schemas by domain entity. All schemas are re-exported
at the package level for backwards compatibility with existing imports.

Usage:
    from schemas import Room, Agent, Message
    # or
    from schemas.room import Room
    from schemas.agent import Agent
"""

from .agent import Agent, AgentBase, AgentCreate, AgentUpdate
from .base import TimestampSerializerMixin
from .message import Message, MessageBase, MessageCreate
from .room import Room, RoomBase, RoomCreate, RoomSummary, RoomUpdate, RoomWithAgents

__all__ = [
    # Base
    "TimestampSerializerMixin",
    # Agent schemas
    "AgentBase",
    "AgentCreate",
    "AgentUpdate",
    "Agent",
    # Message schemas
    "MessageBase",
    "MessageCreate",
    "Message",
    # Room schemas
    "RoomBase",
    "RoomCreate",
    "RoomUpdate",
    "Room",
    "RoomWithAgents",
    "RoomSummary",
]
