"""Agent-related Pydantic schemas."""

from datetime import datetime
from typing import Optional

from i18n.serializers import serialize_bool as _serialize_bool
from i18n.serializers import serialize_utc_datetime as _serialize_utc_datetime
from pydantic import BaseModel, field_serializer


class AgentBase(BaseModel):
    name: str
    group: Optional[str] = None
    config_file: Optional[str] = None
    profile_pic: Optional[str] = None
    in_a_nutshell: Optional[str] = None
    characteristics: Optional[str] = None
    recent_events: Optional[str] = None
    is_critic: bool = False
    interrupt_every_turn: bool = False
    priority: int = 0
    transparent: bool = False


class AgentCreate(AgentBase):
    """
    Create an agent with either:
    1. config_file: Load in_a_nutshell/characteristics/recent_events from file
    2. in_a_nutshell/characteristics/recent_events: Provide directly
    The system_prompt will be built automatically.
    """

    pass


class AgentUpdate(BaseModel):
    """Update agent's runtime fields: nutshell, characteristics, or recent events."""

    profile_pic: Optional[str] = None
    in_a_nutshell: Optional[str] = None
    characteristics: Optional[str] = None
    recent_events: Optional[str] = None


class Agent(AgentBase):
    id: int
    system_prompt: str  # The built system prompt
    session_id: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        return _serialize_utc_datetime(dt)

    @field_serializer("is_critic")
    def serialize_is_critic(self, value: int, _info):
        return _serialize_bool(value)

    @field_serializer("interrupt_every_turn")
    def serialize_interrupt_every_turn(self, value: int, _info):
        return _serialize_bool(value)

    class Config:
        from_attributes = True
