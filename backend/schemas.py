from datetime import datetime
from typing import Any, List, Optional

from domain.enums import ParticipantType
from i18n.serializers import serialize_bool as _serialize_bool
from i18n.serializers import serialize_utc_datetime as _serialize_utc_datetime
from pydantic import BaseModel, field_serializer, model_validator


class TimestampSerializerMixin:
    """Mixin providing common timestamp and boolean serializers for Room schemas."""

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        return _serialize_utc_datetime(dt)

    @field_serializer("last_activity_at")
    def serialize_last_activity_at(self, dt: Optional[datetime], _info):
        return _serialize_utc_datetime(dt) if dt else None

    @field_serializer("last_read_at")
    def serialize_last_read_at(self, dt: Optional[datetime], _info):
        return _serialize_utc_datetime(dt) if dt else None

    @field_serializer("is_paused")
    def serialize_is_paused(self, value: int, _info):
        return _serialize_bool(value)

    @field_serializer("is_finished")
    def serialize_is_finished(self, value: int, _info):
        return _serialize_bool(value)


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


class MessageBase(BaseModel):
    content: str
    role: str
    participant_type: Optional[ParticipantType] = None  # Type of participant (user, character, etc.)
    participant_name: Optional[str] = None  # Custom name for 'character' mode
    image_data: Optional[str] = None  # Base64-encoded image data
    image_media_type: Optional[str] = None  # MIME type (e.g., 'image/png', 'image/jpeg')


class MessageCreate(MessageBase):
    agent_id: Optional[int] = None
    thinking: Optional[str] = None
    anthropic_calls: Optional[List[str]] = None
    mentioned_agent_ids: Optional[List[int]] = None  # Agent IDs from @mentions


class Message(MessageBase):
    id: int
    room_id: int
    agent_id: Optional[int]
    thinking: Optional[str] = None
    anthropic_calls: Optional[List[str]] = None
    timestamp: datetime
    agent_name: Optional[str] = None
    agent_profile_pic: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_agent_fields(cls, data: Any) -> Any:
        """Populate agent_name, agent_profile_pic, and parse anthropic_calls from JSON."""
        # If data is a model instance (has __dict__), extract fields
        if hasattr(data, "__dict__"):
            # Parse anthropic_calls from JSON string if stored (always do this)
            anthropic_calls = None
            if hasattr(data, "anthropic_calls") and data.anthropic_calls:
                import json

                try:
                    anthropic_calls = json.loads(data.anthropic_calls)
                except (json.JSONDecodeError, TypeError):
                    anthropic_calls = None

            # Get the agent relationship if it exists
            agent = getattr(data, "agent", None)

            # Build dict with all fields, including parsed anthropic_calls
            data_dict = {
                "id": data.id,
                "room_id": data.room_id,
                "agent_id": data.agent_id,
                "content": data.content,
                "role": data.role,
                "participant_type": data.participant_type,
                "participant_name": data.participant_name,
                "thinking": data.thinking,
                "anthropic_calls": anthropic_calls,
                "timestamp": data.timestamp,
                "agent_name": agent.name if agent else None,
                "agent_profile_pic": agent.profile_pic if agent else None,
                "image_data": data.image_data,
                "image_media_type": data.image_media_type,
            }
            return data_dict
        return data

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info):
        return _serialize_utc_datetime(dt)

    class Config:
        from_attributes = True


class RoomBase(BaseModel):
    name: str


class RoomCreate(RoomBase):
    max_interactions: Optional[int] = None


class RoomUpdate(BaseModel):
    max_interactions: Optional[int] = None
    is_paused: Optional[bool] = None
    is_finished: Optional[bool] = None


class Room(TimestampSerializerMixin, RoomBase):
    id: int
    owner_id: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: bool = False
    is_finished: bool = False
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
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    has_unread: bool = False

    class Config:
        from_attributes = True
