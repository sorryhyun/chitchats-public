"""
Core application modules.

This package contains core functionality like settings, logging, auth, dependencies,
AgentManager, and service layer functions.

Uses lazy loading for AgentManager and ClientPool to avoid circular import issues.
"""

# Auth exports
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

# Dependency exports
from .dependencies import (
    RequestIdentity,
    ensure_room_access,
    get_agent_manager,
    get_chat_orchestrator,
    get_request_identity,
)

# Exception exports
from .exceptions import (
    AgentNotFoundError,
    ConfigurationError,
    RoomAlreadyExistsError,
    RoomNotFoundError,
)
from .logging import get_logger, setup_logging
from .settings import Settings, get_settings, reset_settings

# Lazy-loaded exports (to avoid circular imports)
_lazy_imports = {
    "AgentManager": "manager",
    "ClientPool": "client_pool",
    "AgentConfigService": "agent_config_service",
    "CacheService": "cache_service",
    "build_system_prompt": "prompt_builder",
}


def __getattr__(name: str):
    """Lazy loading for heavy imports to avoid circular dependencies."""
    if name in _lazy_imports:
        module_name = _lazy_imports[name]
        import importlib

        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
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
    # Lazy-loaded
    "AgentManager",
    "ClientPool",
    "AgentConfigService",
    "CacheService",
    "build_system_prompt",
]
