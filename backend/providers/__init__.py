"""
Multi-provider abstraction layer for AI backends.

This package provides a unified interface for multiple AI providers,
allowing ChitChats to support Claude Code, Codex, and future backends.

Usage:
    from providers import get_provider, ProviderType

    # Get a provider
    provider = get_provider("claude")  # or ProviderType.CLAUDE

    # Build options and create client
    options = provider.build_options(base_options)
    client = provider.create_client(options)
    await client.connect()

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
    AIMessage,
    AIProvider,
    AIStreamEvent,
    AIStreamParser,
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
    "AIMessage",
    "AIProvider",
    "AIStreamEvent",
    "AIStreamParser",
    "ParsedStreamMessage",
    "ProviderType",
    # Factory functions
    "get_provider",
    "get_available_providers",
    "get_default_provider",
    "check_provider_availability",
]
