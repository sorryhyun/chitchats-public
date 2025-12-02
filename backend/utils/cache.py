"""
In-memory caching with TTL support for performance optimization.

This module provides a centralized cache manager for frequently accessed data:
- Agent configuration data (from filesystem)
- Database objects (agents, rooms)
- Recent messages
- Agent profile pictures

All caches support TTL (time-to-live) and manual invalidation.
"""

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger("Cache")

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Single cache entry with value and expiration time."""

    value: Any
    expires_at: float

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() > self.expires_at


class CacheManager:
    """
    Thread-safe in-memory cache with TTL support.

    Features:
    - TTL-based expiration
    - Manual invalidation by key or pattern
    - Automatic cleanup of expired entries
    - Thread-safe operations
    """

    def __init__(self):
        """Initialize cache manager with empty storage."""
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._stats = {"hits": 0, "misses": 0, "invalidations": 0}

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if it exists and hasn't expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]

            # Check if expired
            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                logger.debug(f"Cache expired: {key}")
                return None

            self._stats["hits"] += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float = 60):
        """
        Store value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (default: 60)
        """
        with self._lock:
            expires_at = time.time() + ttl_seconds
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s)")

    def invalidate(self, key: str) -> bool:
        """
        Remove a specific key from cache.

        Args:
            key: Cache key to invalidate

        Returns:
            True if key existed, False otherwise
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["invalidations"] += 1
                logger.debug(f"Cache invalidated: {key}")
                return True
            return False

    def invalidate_pattern(self, pattern: str):
        """
        Invalidate all keys matching a pattern (prefix match).

        Args:
            pattern: Key prefix to match

        Note:
            Current implementation is O(n) where n is cache size.
            For large deployments, consider adding a secondary prefix index
            (trie or dict of prefix->keys) for O(1) pattern lookups.
        """
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
                self._stats["invalidations"] += 1

            if keys_to_delete:
                logger.debug(f"Cache invalidated pattern '{pattern}': {len(keys_to_delete)} keys")

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries removed")

    def cleanup_expired(self):
        """Remove all expired entries from cache."""
        with self._lock:
            current_time = time.time()
            expired_keys = [key for key, entry in self._cache.items() if entry.expires_at < current_time]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"Cache cleanup: {len(expired_keys)} expired entries removed")

    def get_or_set(self, key: str, factory: Callable[[], T], ttl_seconds: float = 60) -> T:
        """
        Get value from cache or compute it if not found.

        Args:
            key: Cache key
            factory: Function to compute value if not cached
            ttl_seconds: Time to live in seconds

        Returns:
            Cached or computed value
        """
        # Try to get from cache first
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value

        # Compute value
        value = factory()

        # Store in cache
        self.set(key, value, ttl_seconds)

        return value

    async def get_or_set_async(self, key: str, factory: Callable[[], Any], ttl_seconds: float = 60) -> Any:
        """
        Async version of get_or_set.

        Args:
            key: Cache key
            factory: Async function to compute value if not cached
            ttl_seconds: Time to live in seconds

        Returns:
            Cached or computed value
        """
        # Try to get from cache first
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value

        # Compute value (async)
        value = await factory()

        # Store in cache
        self.set(key, value, ttl_seconds)

        return value

    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Note:
            For production monitoring, consider exporting these stats
            as prometheus metrics using prometheus_client library:
            - cache_hits_total (counter)
            - cache_misses_total (counter)
            - cache_size (gauge)
            - cache_hit_rate (gauge)
        """
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0

            return {**self._stats, "total_requests": total, "hit_rate": round(hit_rate, 2), "size": len(self._cache)}

    def log_stats(self):
        """Log current cache statistics."""
        stats = self.get_stats()
        logger.info(
            f"Cache stats: {stats['hits']} hits, {stats['misses']} misses, "
            f"{stats['hit_rate']}% hit rate, {stats['size']} entries, "
            f"{stats['invalidations']} invalidations"
        )


# Global cache instance
_cache_manager = CacheManager()


def get_cache() -> CacheManager:
    """Get the global cache manager instance."""
    return _cache_manager


# Cache key builders for consistent naming
def agent_config_key(agent_id: int) -> str:
    """Build cache key for agent config data."""
    return f"agent_config:{agent_id}"


def agent_object_key(agent_id: int) -> str:
    """Build cache key for agent database object."""
    return f"agent_obj:{agent_id}"


def room_object_key(room_id: int) -> str:
    """Build cache key for room database object."""
    return f"room_obj:{room_id}"


def room_agents_key(room_id: int) -> str:
    """Build cache key for room's agents list."""
    return f"room_agents:{room_id}"


def room_messages_key(room_id: int) -> str:
    """Build cache key for room's messages."""
    return f"room_messages:{room_id}"


def chatting_agents_key(room_id: int) -> str:
    """Build cache key for currently chatting agents."""
    return f"chatting_agents:{room_id}"
