"""
Multi-provider abstraction layer for AI backends.

This package provides a unified interface for multiple AI providers,
allowing ChitChats to support Claude Code, Codex, and future backends.

Usage:
    from providers import get_provider, ProviderType

    # Get a provider
    provider = get_provider("claude")  # or ProviderType.CLAUDE

    # Build options and get a pooled client
    options = provider.build_options(base_options)
    client, is_new = await provider.get_client_pool().get_or_create(task_id, options)

    # Send message and receive response
    await client.query("Hello!")
    async for message in client.receive_response():
        parsed = provider.get_parser().parse_message(message, "", "")
        print(parsed.response_text)

    await client.disconnect()
"""

from .base import (
    AIClient,
    AIClientOptions,
    AIProvider,
    AIStreamParser,
    ClientPoolInterface,
    ParsedStreamMessage,
    ProviderType,
)
from .factory import (
    check_provider_availability,
    get_available_providers,
    get_default_provider,
    get_provider,
)

__all__ = [
    # Base classes
    "AIClient",
    "AIClientOptions",
    "AIProvider",
    "AIStreamParser",
    "ClientPoolInterface",
    "ParsedStreamMessage",
    "ProviderType",
    # Factory functions
    "get_provider",
    "get_available_providers",
    "get_default_provider",
    "check_provider_availability",
]
