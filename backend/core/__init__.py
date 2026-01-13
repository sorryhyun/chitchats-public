"""
Core application modules.

This package contains core functionality like settings, logging, auth, dependencies,
and agent management infrastructure.
"""

from .logging import get_logger, setup_logging
from .settings import Settings, get_settings, reset_settings

# Lazy import to avoid circular dependency
# AgentManager imports from providers which imports from core.config
# which in turn may need core.settings


def __getattr__(name: str):
    """Lazy import for AgentManager to avoid circular import."""
    if name == "AgentManager":
        from .manager import AgentManager
        return AgentManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Settings and logging
    "Settings",
    "get_settings",
    "reset_settings",
    "setup_logging",
    "get_logger",
    # Agent management (lazy loaded)
    "AgentManager",
]
