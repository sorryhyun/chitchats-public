"""
Debug and monitoring endpoints.

These endpoints provide access to cache statistics and other debugging information.
"""

from typing import Dict

from core import require_admin
from core.cache_service import get_cache_service
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/cache/stats", dependencies=[Depends(require_admin)])
async def get_cache_stats() -> Dict[str, int]:
    """
    Get current cache statistics.

    Returns:
        Dictionary containing:
        - hits: Number of cache hits
        - misses: Number of cache misses
        - total_requests: Total cache requests
        - hit_rate: Cache hit rate percentage
        - size: Number of entries in cache
        - invalidations: Number of cache invalidations
    """
    cache_service = get_cache_service()
    return cache_service.get_stats()


@router.post("/cache/cleanup", dependencies=[Depends(require_admin)])
async def cleanup_cache() -> Dict[str, str]:
    """
    Manually trigger cache cleanup to remove expired entries.

    Returns:
        Success message
    """
    cache_service = get_cache_service()
    cache_service.cleanup_expired()
    return {"status": "success", "message": "Cache cleanup completed"}


@router.post("/cache/clear", dependencies=[Depends(require_admin)])
async def clear_cache() -> Dict[str, str]:
    """
    Clear all cache entries.

    WARNING: This will clear the entire cache and may temporarily impact performance.

    Returns:
        Success message
    """
    cache_service = get_cache_service()
    cache_service.clear()
    return {"status": "success", "message": "Cache cleared successfully"}
