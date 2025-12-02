"""
Cache service layer for consistent cache access and invalidation.

This module provides a service layer that wraps the cache manager and ensures
that write operations properly invalidate related cache entries.
"""

import logging
from typing import Any, Callable, Dict, Optional, TypeVar

from utils.cache import (
    CacheManager,
    agent_config_key,
    agent_object_key,
    chatting_agents_key,
    get_cache,
    room_agents_key,
    room_messages_key,
    room_object_key,
)

logger = logging.getLogger("CacheService")

T = TypeVar("T")


class CacheService:
    """
    Service layer for cache operations with automatic invalidation.

    This service provides a high-level interface to the cache manager
    and ensures that write operations properly invalidate related cache entries.
    """

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """
        Initialize cache service.

        Args:
            cache_manager: Optional CacheManager instance (uses global if not provided)
        """
        self._cache = cache_manager or get_cache()

    # Read operations

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: float = 60):
        """Set value in cache with TTL."""
        self._cache.set(key, value, ttl_seconds)

    def get_or_set(self, key: str, factory: Callable[[], T], ttl_seconds: float = 60) -> T:
        """Get value from cache or compute if not found."""
        return self._cache.get_or_set(key, factory, ttl_seconds)

    async def get_or_set_async(self, key: str, factory: Callable[[], Any], ttl_seconds: float = 60) -> Any:
        """Async version of get_or_set."""
        return await self._cache.get_or_set_async(key, factory, ttl_seconds)

    # Invalidation operations

    def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache key."""
        return self._cache.invalidate(key)

    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching a pattern (prefix match)."""
        self._cache.invalidate_pattern(pattern)

    def invalidate_agent(self, agent_id: int):
        """
        Invalidate all cache entries related to an agent.

        This should be called when:
        - Agent is created, updated, or deleted
        - Agent configuration is reloaded
        """
        keys = [agent_object_key(agent_id), agent_config_key(agent_id)]
        for key in keys:
            self._cache.invalidate(key)
        logger.debug(f"Invalidated cache for agent {agent_id}")

    def invalidate_room(self, room_id: int):
        """
        Invalidate all cache entries related to a room.

        This should be called when:
        - Room is created, updated, or deleted
        - Room settings change (paused, max_interactions)
        """
        keys = [room_object_key(room_id), room_agents_key(room_id), chatting_agents_key(room_id)]
        for key in keys:
            self._cache.invalidate(key)
        # Also invalidate message cache pattern
        self._cache.invalidate_pattern(room_messages_key(room_id))
        logger.debug(f"Invalidated cache for room {room_id}")

    def invalidate_room_agents(self, room_id: int):
        """
        Invalidate room agents cache.

        This should be called when:
        - Agents are added to or removed from a room
        """
        self._cache.invalidate(room_agents_key(room_id))
        logger.debug(f"Invalidated room agents cache for room {room_id}")

    def invalidate_room_messages(self, room_id: int):
        """
        Invalidate message cache for a room.

        This should be called when:
        - New messages are created
        """
        self._cache.invalidate_pattern(room_messages_key(room_id))
        logger.debug(f"Invalidated message cache for room {room_id}")

    # Maintenance operations

    def cleanup_expired(self):
        """Remove all expired entries from cache."""
        self._cache.cleanup_expired()

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()

    # Statistics and monitoring

    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hits, misses, hit_rate, size, invalidations
        """
        return self._cache.get_stats()

    def log_stats(self):
        """Log current cache statistics."""
        self._cache.log_stats()


# Global cache service instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get the global cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


def reset_cache_service():
    """Reset the cache service instance (useful for testing)."""
    global _cache_service
    _cache_service = None
