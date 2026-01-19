from datetime import datetime
from typing import Optional

from i18n.serializers import serialize_bool as _serialize_bool
from i18n.serializers import serialize_utc_datetime as _serialize_utc_datetime
from pydantic import BaseModel, field_serializer


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


class ImageItem(BaseModel):
    """Single image in a message."""

    data: str  # Base64-encoded image data
    media_type: str  # MIME type (e.g., 'image/png', 'image/webp')
