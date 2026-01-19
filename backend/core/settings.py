"""
Centralized application settings using Pydantic BaseSettings.

This module provides type-safe access to environment variables with validation.
All settings are loaded once at application startup.
"""

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings

# ============================================================================
# Application Constants
# ============================================================================

# Default fallback prompt if no configuration is provided
DEFAULT_FALLBACK_PROMPT = "You are a helpful AI assistant."

# Skip message text (displayed when agent chooses not to respond)
SKIP_MESSAGE_TEXT = "(무시함)"

# Bundled Codex binary paths by platform (relative to project root)
BUNDLED_CODEX_PATHS: Dict[str, str] = {
    "windows-amd64": "bundled/codex-x86_64-pc-windows-msvc.exe",
    "windows-x86_64": "bundled/codex-x86_64-pc-windows-msvc.exe",
    "darwin-arm64": "bundled/codex-aarch64-apple-darwin",
    "darwin-x86_64": "bundled/codex-x86_64-apple-darwin",
    "linux-x86_64": "bundled/codex-x86_64-unknown-linux-gnu",
    "linux-aarch64": "bundled/codex-aarch64-unknown-linux-gnu",
}

# Character-specific MCP tool names organized by group
# These are the tools available to each agent for character-based interactions
AGENT_TOOL_NAMES_BY_GROUP: Dict[str, Dict[str, str]] = {
    "action": {
        "skip": "mcp__action__skip",
        "memorize": "mcp__action__memorize",
        "recall": "mcp__action__recall",
    },
    "character": {
        "memory_select": "mcp__character__character_identity",
    },
    "guidelines": {
        "read": "mcp__guidelines__read",
        "anthropic": "mcp__guidelines__anthropic",
    },
}

# Backward compatibility: Flat dictionary for legacy code
AGENT_TOOL_NAMES = {
    tool_key: tool_name
    for group_tools in AGENT_TOOL_NAMES_BY_GROUP.values()
    for tool_key, tool_name in group_tools.items()
}


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings have sensible defaults and are validated on startup.
    """

    # Authentication
    api_key_hash: Optional[str] = None
    jwt_secret: Optional[str] = None
    guest_password_hash: Optional[str] = None
    enable_guest_login: bool = True

    # User configuration
    user_name: str = "User"

    # Agent priority system
    priority_agents: str = ""

    # CORS configuration
    frontend_url: Optional[str] = None
    vercel_url: Optional[str] = None

    # Guidelines system
    guidelines_file: str = "guidelines_3rd"

    # Model configuration
    use_haiku: bool = False

    # Debug configuration
    debug_agents: bool = False

    # Experimental features
    experimental_custom_cli: bool = False

    # Background scheduler configuration
    max_concurrent_rooms: int = 5

    # Codex provider configuration
    codex_model: str = "gpt-5.2"  # Default model for Codex provider

    @field_validator("enable_guest_login", mode="before")
    @classmethod
    def validate_enable_guest_login(cls, v: Optional[str]) -> bool:
        """Parse enable_guest_login from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() == "true"
        return True

    @field_validator("use_haiku", mode="before")
    @classmethod
    def validate_use_haiku(cls, v: Optional[str]) -> bool:
        """Parse use_haiku from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() == "true"
        return False

    @field_validator("debug_agents", mode="before")
    @classmethod
    def validate_debug_agents(cls, v: Optional[str]) -> bool:
        """Parse debug_agents from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() == "true"
        return False

    @field_validator("experimental_custom_cli", mode="before")
    @classmethod
    def validate_experimental_custom_cli(cls, v: Optional[str]) -> bool:
        """Parse experimental_custom_cli from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() == "true"
        return False

    def get_priority_agent_names(self) -> List[str]:
        """
        Get the list of priority agent names from the PRIORITY_AGENTS setting.

        Returns:
            List of agent names that should have priority in responding
        """
        if not self.priority_agents:
            return []
        # Split by comma and strip whitespace from each name
        return [name.strip() for name in self.priority_agents.split(",") if name.strip()]

    @property
    def project_root(self) -> Path:
        """
        Get the project root directory (parent of backend/).

        Returns:
            Path to the project root directory
        """
        backend_dir = Path(__file__).parent.parent
        return backend_dir.parent

    @property
    def backend_dir(self) -> Path:
        """
        Get the backend directory.

        Returns:
            Path to the backend directory
        """
        return Path(__file__).parent.parent

    @property
    def agents_dir(self) -> Path:
        """
        Get the agents configuration directory.

        Returns:
            Path to the agents directory
        """
        return self.project_root / "agents"

    @property
    def config_dir(self) -> Path:
        """
        Get the general configuration files directory.

        Returns:
            Path to backend/config directory (for debug.yaml, conversation_context.yaml)
        """
        return self.backend_dir / "config"

    @property
    def mcp_servers_config_dir(self) -> Path:
        """
        Get the MCP servers configuration directory.

        Returns:
            Path to backend/mcp_servers/config directory (for tools.yaml, guidelines)
        """
        return self.backend_dir / "mcp_servers" / "config"

    @property
    def tools_config_path(self) -> Path:
        """
        Get the path to tools.yaml configuration file.

        Returns:
            Path to tools.yaml
        """
        return self.mcp_servers_config_dir / "tools.yaml"

    @property
    def debug_config_path(self) -> Path:
        """
        Get the path to debug.yaml configuration file.

        Returns:
            Path to debug.yaml
        """
        return self.config_dir / "debug.yaml"

    @property
    def conversation_context_config_path(self) -> Path:
        """
        Get the path to conversation_context.yaml configuration file.

        Returns:
            Path to conversation_context.yaml
        """
        return self.config_dir / "conversation_context.yaml"

    @property
    def system_prompt_config_path(self) -> Path:
        """
        Get the path to the system prompt configuration file.

        Returns:
            Path to system_prompt.yaml in backend/config/
        """
        return self.config_dir / "system_prompt.yaml"

    @property
    def guidelines_config_path(self) -> Path:
        """
        Get the path to the guidelines tool configuration file.

        Returns:
            Path to guidelines.yaml
        """
        return self.mcp_servers_config_dir / "guidelines.yaml"

    def get_cors_origins(self) -> List[str]:
        """
        Get the list of allowed CORS origins.

        Returns:
            List of allowed origin URLs
        """
        origins = [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]

        # Add custom frontend URL if provided
        if self.frontend_url:
            origins.append(self.frontend_url)

        # Add Vercel URL if provided (auto-detected on Vercel)
        if self.vercel_url:
            origins.append(f"https://{self.vercel_url}")

        # Add local network IPs for development
        import socket

        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            origins.extend([f"http://{local_ip}:5173", f"http://{local_ip}:5174"])
        except Exception:
            pass

        return origins

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Allow extra fields for forward compatibility
        extra = "ignore"


# Singleton instance - load settings once at module import
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the application settings singleton.

    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        # Create settings instance first (to access path properties)
        _settings = Settings()

        # Find .env file in project root using settings path properties
        env_path = _settings.project_root / ".env"

        # Reload settings with explicit env file path if it exists
        if env_path.exists():
            _settings = Settings(_env_file=str(env_path))

    return _settings


def reset_settings() -> None:
    """
    Reset the settings singleton (useful for testing).
    """
    global _settings
    _settings = None
