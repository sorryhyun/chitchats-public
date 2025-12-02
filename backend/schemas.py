from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_serializer, model_validator
from utils.serializers import serialize_sqlite_bool as _serialize_sqlite_bool
from utils.serializers import serialize_utc_datetime as _serialize_utc_datetime

# Input length limits to prevent DoS and database bloat
MAX_NAME_LENGTH = 100
MAX_GROUP_LENGTH = 100
MAX_PATH_LENGTH = 500
MAX_PROFILE_PIC_LENGTH = 50000  # Data URLs can be large
MAX_NUTSHELL_LENGTH = 10000
MAX_CHARACTERISTICS_LENGTH = 50000
MAX_RECENT_EVENTS_LENGTH = 20000
MAX_MESSAGE_CONTENT_LENGTH = 100000
MAX_THINKING_LENGTH = 200000
MAX_ROLE_LENGTH = 50
MAX_PARTICIPANT_TYPE_LENGTH = 50
MAX_ROOM_NAME_LENGTH = 200
MAX_IMAGE_DATA_LENGTH = 20000000  # ~15MB base64 (images can be large)


class ImageAttachment(BaseModel):
    """Image attachment with base64-encoded data."""

    data: str = Field(..., max_length=MAX_IMAGE_DATA_LENGTH)
    media_type: str = Field(..., max_length=50)  # e.g., 'image/png', 'image/jpeg'


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    group: Optional[str] = Field(None, max_length=MAX_GROUP_LENGTH)
    config_file: Optional[str] = Field(None, max_length=MAX_PATH_LENGTH)
    profile_pic: Optional[str] = Field(None, max_length=MAX_PROFILE_PIC_LENGTH)
    in_a_nutshell: Optional[str] = Field(None, max_length=MAX_NUTSHELL_LENGTH)
    characteristics: Optional[str] = Field(None, max_length=MAX_CHARACTERISTICS_LENGTH)
    recent_events: Optional[str] = Field(None, max_length=MAX_RECENT_EVENTS_LENGTH)
    is_critic: bool = False


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

    profile_pic: Optional[str] = Field(None, max_length=MAX_PROFILE_PIC_LENGTH)
    in_a_nutshell: Optional[str] = Field(None, max_length=MAX_NUTSHELL_LENGTH)
    characteristics: Optional[str] = Field(None, max_length=MAX_CHARACTERISTICS_LENGTH)
    recent_events: Optional[str] = Field(None, max_length=MAX_RECENT_EVENTS_LENGTH)


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
        return _serialize_sqlite_bool(value)

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CONTENT_LENGTH)
    role: str = Field(..., min_length=1, max_length=MAX_ROLE_LENGTH)
    participant_type: Optional[str] = Field(None, max_length=MAX_PARTICIPANT_TYPE_LENGTH)
    participant_name: Optional[str] = Field(None, max_length=MAX_NAME_LENGTH)
    image_data: Optional[ImageAttachment] = None  # Optional image attachment


class MessageCreate(MessageBase):
    agent_id: Optional[int] = None
    thinking: Optional[str] = Field(None, max_length=MAX_THINKING_LENGTH)


class Message(MessageBase):
    id: int
    room_id: int
    agent_id: Optional[int]
    thinking: Optional[str] = None
    timestamp: datetime
    agent_name: Optional[str] = None
    agent_profile_pic: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_agent_fields(cls, data: Any) -> Any:
        """Populate agent_name and agent_profile_pic from the agent relationship."""
        # If data is a model instance (has __dict__), extract agent info
        if hasattr(data, "__dict__"):
            # Get the agent relationship if it exists
            agent = getattr(data, "agent", None)
            if agent:
                # Parse image_data from JSON string if stored in DB
                image_data_raw = getattr(data, "image_data", None)
                image_data = None
                if image_data_raw:
                    import json

                    try:
                        image_data = json.loads(image_data_raw) if isinstance(image_data_raw, str) else image_data_raw
                    except (json.JSONDecodeError, TypeError):
                        pass
                # Create a dict from the model and add agent fields
                data_dict = {
                    "id": data.id,
                    "room_id": data.room_id,
                    "agent_id": data.agent_id,
                    "content": data.content,
                    "role": data.role,
                    "participant_type": data.participant_type,
                    "participant_name": data.participant_name,
                    "thinking": data.thinking,
                    "timestamp": data.timestamp,
                    "agent_name": agent.name,
                    "agent_profile_pic": agent.profile_pic,
                    "image_data": image_data,
                }
                return data_dict
            else:
                # No agent relationship, but still need to handle image_data
                image_data_raw = getattr(data, "image_data", None)
                if image_data_raw and isinstance(image_data_raw, str):
                    import json

                    try:
                        data_dict = {
                            k: getattr(data, k, None)
                            for k in [
                                "id",
                                "room_id",
                                "agent_id",
                                "content",
                                "role",
                                "participant_type",
                                "participant_name",
                                "thinking",
                                "timestamp",
                            ]
                        }
                        data_dict["image_data"] = json.loads(image_data_raw)
                        return data_dict
                    except (json.JSONDecodeError, TypeError):
                        pass
        return data

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info):
        return _serialize_utc_datetime(dt)

    class Config:
        from_attributes = True


class RoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_ROOM_NAME_LENGTH)


class RoomCreate(RoomBase):
    max_interactions: Optional[int] = None


class RoomUpdate(BaseModel):
    max_interactions: Optional[int] = None
    is_paused: Optional[bool] = None


class Room(RoomBase):
    id: int
    owner_id: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: bool = False
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    agents: List[Agent] = []
    messages: List[Message] = []

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
        return _serialize_sqlite_bool(value)

    class Config:
        from_attributes = True


class RoomSummary(RoomBase):
    id: int
    owner_id: Optional[str] = None
    max_interactions: Optional[int] = None
    is_paused: bool = False
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    last_read_at: Optional[datetime] = None
    has_unread: bool = False

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
        return _serialize_sqlite_bool(value)

    class Config:
        from_attributes = True
