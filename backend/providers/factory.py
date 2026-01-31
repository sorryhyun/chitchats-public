"""
Provider factory for creating AI provider instances.

This module provides the factory function for instantiating AI providers
based on provider type string.
"""

import logging

from .base import AIProvider, ProviderType

logger = logging.getLogger("ProviderFactory")

# Lazy-loaded provider instances (singletons)
_providers: dict[ProviderType, AIProvider] = {}


def get_provider(provider_type: str | ProviderType) -> AIProvider:
    """Get an AI provider instance by type.

    Args:
        provider_type: Provider type string ("claude", "codex") or ProviderType enum

    Returns:
        AIProvider instance for the requested type

    Raises:
        ValueError: If provider type is not supported
    """
    # Normalize to ProviderType enum
    if isinstance(provider_type, str):
        try:
            provider_type = ProviderType(provider_type.lower())
        except ValueError:
            raise ValueError(
                f"Unknown provider type: {provider_type}. Supported types: {[p.value for p in ProviderType]}"
            )

    # Return cached instance if available
    if provider_type in _providers:
        return _providers[provider_type]

    # Create new provider instance
    if provider_type == ProviderType.CLAUDE:
        from .claude import ClaudeProvider

        provider = ClaudeProvider()
    elif provider_type == ProviderType.CODEX:
        from .codex import CodexProvider

        provider = CodexProvider()
    elif provider_type == ProviderType.CUSTOM:
        from .custom import CustomProvider

        provider = CustomProvider()
    else:
        raise ValueError(f"Provider type {provider_type} is not implemented")

    # Cache and return
    _providers[provider_type] = provider
    logger.info(f"Created {provider_type.value} provider instance")
    return provider


async def check_provider_availability(provider_type: str | ProviderType) -> bool:
    """Check if a provider is available and authenticated.

    Args:
        provider_type: Provider type to check

    Returns:
        True if provider is ready to use
    """
    try:
        provider = get_provider(provider_type)
        return await provider.check_availability()
    except Exception as e:
        logger.warning(f"Provider {provider_type} availability check failed: {e}")
        return False


def get_available_providers() -> list[ProviderType]:
    """Get list of all supported provider types.

    Note: This returns all supported types, not necessarily available ones.
    Use check_provider_availability() to verify actual availability.

    Returns:
        List of supported ProviderType values
    """
    return list(ProviderType)


def get_default_provider() -> ProviderType:
    """Get the default provider type.

    Returns:
        ProviderType.CLAUDE as the default
    """
    return ProviderType.CLAUDE
