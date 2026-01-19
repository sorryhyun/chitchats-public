"""
Providers API endpoints.

Provides endpoints for listing available AI providers and checking their status.
"""

from fastapi import APIRouter
from providers import check_provider_availability

router = APIRouter()


@router.get("/providers")
async def get_providers():
    """Get list of available AI providers and their status.

    Returns:
        dict containing:
        - providers: List of provider objects with name and availability status
        - default: The default provider name
    """
    codex_available = await check_provider_availability("codex")

    return {
        "providers": [
            {"name": "claude", "available": True},  # Always available via SDK
            {"name": "codex", "available": codex_available},
        ],
        "default": "claude",
    }
