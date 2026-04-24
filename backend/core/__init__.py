"""
Core application modules.

This package contains core functionality like settings, logging, auth,
dependencies, AgentManager, and service layer functions.
"""

from .agent_config_service import AgentConfigService
from .auth import (
    AuthMiddleware,
    generate_jwt_token,
    get_role_from_token,
    get_user_id_from_token,
    require_admin,
    validate_api_key,
    validate_jwt_token,
    validate_password_with_role,
)
from .cache_service import CacheService
from .client_pool import ClientPool
from .dependencies import (
    RequestIdentity,
    ensure_room_access,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
)
from .exceptions import (
    AgentNotFoundError,
    ConfigurationError,
    RoomAlreadyExistsError,
    RoomNotFoundError,
)
from .logging import get_logger, setup_logging
from .manager import AgentManager
from .settings import Settings, get_settings, reset_settings


def __getattr__(name: str):
    """Defer config-validation imports — pulling them eagerly creates a cycle
    via mcp_servers.config.loaders → core.get_settings during package init."""
    if name in {"log_config_validation", "reload_all_configs", "validate_config_schema"}:
        from mcp_servers.config import validation

        return getattr(validation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Settings
    "Settings",
    "get_settings",
    "reset_settings",
    # Logging
    "setup_logging",
    "get_logger",
    # Auth
    "AuthMiddleware",
    "generate_jwt_token",
    "get_role_from_token",
    "get_user_id_from_token",
    "require_admin",
    "validate_api_key",
    "validate_jwt_token",
    "validate_password_with_role",
    # Exceptions
    "AgentNotFoundError",
    "ConfigurationError",
    "RoomAlreadyExistsError",
    "RoomNotFoundError",
    # Dependencies
    "RequestIdentity",
    "ensure_room_access",
    "get_agent_manager",
    "get_chat_orchestrator",
    "get_request_identity",
    # Services / managers
    "AgentManager",
    "ClientPool",
    "AgentConfigService",
    "CacheService",
    # Lazy (mcp_servers.config.validation)
    "log_config_validation",
    "reload_all_configs",
    "validate_config_schema",
]
