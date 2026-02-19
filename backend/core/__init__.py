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
from .settings import Settings, get_settings, get_use_sonnet, reset_settings, set_use_sonnet

# Lazy-loaded exports (to avoid circular imports)
_lazy_imports = {
    "AgentManager": "manager",
    "ClientPool": "client_pool",
    "AgentConfigService": "agent_config_service",
    "CacheService": "cache_service",
    "build_system_prompt": "prompt_builder",
    # Config validation (lazy to avoid circular imports with mcp_servers.config)
    "log_config_validation": "mcp_servers.config.validation",
    "reload_all_configs": "mcp_servers.config.validation",
    "validate_config_schema": "mcp_servers.config.validation",
}


def __getattr__(name: str):
    """Lazy loading for heavy imports to avoid circular dependencies."""
    if name in _lazy_imports:
        module_name = _lazy_imports[name]
        import importlib

        # Use absolute import for external packages, relative for core submodules
        if "." in module_name and not module_name.startswith("core."):
            module = importlib.import_module(module_name)
        else:
            module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Settings
    "Settings",
    "get_settings",
    "get_use_sonnet",
    "reset_settings",
    "set_use_sonnet",
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
    # Config validation (lazy-loaded)
    "log_config_validation",
    "reload_all_configs",
    "validate_config_schema",
]
