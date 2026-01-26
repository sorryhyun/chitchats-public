from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .agent import Agent
from .base import TimestampSerializerMixin
from .message import Message


class RoomBase(BaseModel):
    name: str


class RoomCreate(RoomBase):
    max_interactions: Optional[int] = None
    provider: Optional[str] = "claude"  # AI provider: 'claude' or 'codex'


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: Optional[bool] = None
    is_finished: Optional[bool] = None


class Room(TimestampSerializerMixin, RoomBase):
    id: int
    owner_id: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: bool = False
    is_finished: bool = False
    default_provider: str = "claude"  # AI provider: 'claude' or 'codex'
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    agents: List[Agent] = []
    messages: List[Message] = []

    class Config:
        from_attributes = True


class RoomSummary(TimestampSerializerMixin, RoomBase):
    id: int
    owner_id: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: bool = False
    is_finished: bool = False
    default_provider: str = "claude"  # AI provider: 'claude' or 'codex'
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    has_unread: bool = False

    class Config:
        from_attributes = True
