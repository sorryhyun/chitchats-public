"""
CRUD operations module.

This module provides database operations organized by domain aggregate.
All CRUD functions are exported at the package level for backward compatibility.
"""

# Room operations
# Agent operations
from .agents import (
    append_agent_memory,
    create_agent,
    delete_agent,
    get_agent,
    get_agents_by_ids,
    get_all_agents,
    reload_agent_from_config,
    seed_agents_from_configs,
    update_agent,
)

# Cached operations
from .cached import (
    get_agent_cached,
    get_agents_cached,
    get_messages_after_agent_response_cached,
    get_messages_cached,
    get_messages_since_cached,
    get_recent_messages_cached,
    get_room_cached,
    invalidate_agent_cache,
    invalidate_messages_cache,
    invalidate_room_cache,
)

# Message operations
from .messages import (
    create_message,
    delete_room_messages,
    get_critic_messages,
    get_messages,
    get_messages_after_agent_response,
    get_messages_since,
    get_recent_messages,
)

# Room-Agent relationship operations
from .room_agents import (
    add_agent_to_room,
    get_agents,
    get_room_agent_session,
    remove_agent_from_room,
    update_room_agent_session,
)
from .rooms import (
    create_room,
    delete_room,
    get_or_create_direct_room,
    get_room,
    get_rooms,
    mark_room_as_read,
    update_room,
)

# Export all functions
__all__ = [
    # Room operations
    "create_room",
    "get_rooms",
    "get_room",
    "update_room",
    "mark_room_as_read",
    "delete_room",
    "get_or_create_direct_room",
    # Agent operations
    "create_agent",
    "get_all_agents",
    "get_agents_by_ids",
    "get_agent",
    "delete_agent",
    "update_agent",
    "reload_agent_from_config",
    "append_agent_memory",
    "seed_agents_from_configs",
    # Message operations
    "create_message",
    "get_messages",
    "get_messages_since",
    "get_recent_messages",
    "get_messages_after_agent_response",
    "get_critic_messages",
    "delete_room_messages",
    # Room-Agent relationship operations
    "get_agents",
    "add_agent_to_room",
    "remove_agent_from_room",
    "get_room_agent_session",
    "update_room_agent_session",
    # Cached operations
    "get_agent_cached",
    "get_room_cached",
    "get_agents_cached",
    "get_messages_cached",
    "get_recent_messages_cached",
    "get_messages_since_cached",
    "get_messages_after_agent_response_cached",
    "invalidate_room_cache",
    "invalidate_agent_cache",
    "invalidate_messages_cache",
]
