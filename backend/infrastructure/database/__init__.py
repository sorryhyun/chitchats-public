"""
Database infrastructure: models, migrations, connection, and utilities.

This module re-exports from the centralized database.py for backward compatibility.
"""

# Import from centralized database module
from database import (
    Base,
    SerializedWrite,
    get_db,
    get_engine,
    get_session_maker,
    init_db,
    is_sqlite,
    retry_on_db_lock,
    serialized_commit,
    serialized_write,
    shutdown_db,
)

from . import models
from .models import Agent, Message, Room, RoomAgentSession, room_agents


# Legacy module-level accessors using __getattr__
def __getattr__(name):
    """Lazy access for legacy module-level attributes."""
    if name == "engine":
        return get_engine()
    if name == "async_session_maker":
        return get_session_maker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models
    "models",
    "Agent",
    "Message",
    "Room",
    "RoomAgentSession",
    "room_agents",
    # Connection
    "Base",
    "engine",
    "async_session_maker",
    "get_db",
    "init_db",
    "shutdown_db",
    "is_sqlite",
    "get_engine",
    "get_session_maker",
    # Concurrency helpers
    "retry_on_db_lock",
    "SerializedWrite",
    "serialized_write",
    "serialized_commit",
]
