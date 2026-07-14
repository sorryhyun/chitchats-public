import json
from datetime import datetime
from typing import Any, List, Optional

from domain.enums import ParticipantType
from i18n.serializers import serialize_utc_datetime as _serialize_utc_datetime
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .base import ImageItem


class MessageBase(BaseModel):
    content: str
    role: str
    participant_type: Optional[ParticipantType] = None  # Type of participant (user, character, etc.)
    participant_name: Optional[str] = None  # Custom name for 'character' mode
    images: Optional[List[ImageItem]] = None  # Multiple images (up to 5)
    # DEPRECATED: Keep for backward compatibility during migration
    image_data: Optional[str] = None
    image_media_type: Optional[str] = None


class MessageCreate(MessageBase):
    agent_id: Optional[int] = None
    thinking: Optional[str] = None
    anthropic_calls: Optional[List[str]] = None
    excuse_reasons: Optional[List[str]] = None
    mentioned_agent_ids: Optional[List[int]] = None  # Agent IDs from @mentions
    provider: Optional[str] = None  # AI provider that produced this message


class Message(MessageBase):
    """A stored message, validated straight off the ORM row via `from_attributes`.

    The `anthropic_calls`, `excuse_reasons` and `images` columns are TEXT holding a
    JSON array; the agent fields are flattened from the `agent` relationship (which
    must be eager-loaded, or is None for user/system messages).
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    room_id: int
    agent_id: Optional[int]
    thinking: Optional[str] = None
    anthropic_calls: Optional[List[str]] = None
    excuse_reasons: Optional[List[str]] = None
    timestamp: datetime
    agent_name: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("agent_name", AliasPath("agent", "name"))
    )
    agent_profile_pic: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("agent_profile_pic", AliasPath("agent", "profile_pic"))
    )
    provider: Optional[str] = None

    @field_validator("anthropic_calls", "excuse_reasons", "images", mode="before")
    @classmethod
    def parse_json_column(cls, value: Any) -> Any:
        """Decode the JSON-array TEXT columns; malformed content degrades to None."""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    @model_validator(mode="after")
    def backfill_legacy_image(self):
        """Surface pre-`images` rows (single base64 blob) through the `images` list."""
        if not self.images and self.image_data and self.image_media_type:
            self.images = [ImageItem(data=self.image_data, media_type=self.image_media_type)]
        return self

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info):
        return _serialize_utc_datetime(dt)
