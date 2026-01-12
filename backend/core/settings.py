"""
Centralized application settings using Pydantic BaseSettings.

This module provides type-safe access to environment variables with validation.
All settings are loaded once at application startup.
"""

import sys
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


def _is_frozen() -> bool:
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _get_base_path() -> Path:
    """Get the base path for bundled resources (handles both dev and bundled modes)."""
    if _is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent.parent.parent  # backend/core -> backend -> project_root


def _get_work_dir() -> Path:
    """Get the working directory for user data (agents, .env, etc.)."""
    if _is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent  # backend/core -> backend -> project_root

# ============================================================================
# Application Constants
# ============================================================================

# Default fallback prompt if no configuration is provided
DEFAULT_FALLBACK_PROMPT = "You are a helpful AI assistant."

# Skip message text (displayed when agent chooses not to respond)
SKIP_MESSAGE_TEXT = "(무시함)"

# Claude Agent SDK Tool Configuration
# These are the built-in tools provided by Claude Agent SDK that we want to disallow
# to ensure agents stay in character and use only their character-specific tools
# BUILTIN_TOOLS = [
#     "Task",
#     "Bash",
#     "Glob",
#     "Grep",
#     "ExitPlanMode",
#     "Read",
#     "Edit",
#     "Write",
#     "NotebookEdit",
#     "WebFetch",
#     "TodoWrite",
#     "WebSearch",
#     "BashOutput",
#     "KillShell",
#     "Skill",
#     "SlashCommand",
#     "ListMcpResources",
# ]

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

    # Memory system
    recall_memory_file: str = "consolidated_memory"

    # Guidelines system
    read_guideline_by: Literal["description", "active_tool"] = "active_tool"
    guidelines_file: str = "guidelines_3rd"

    # Model configuration
    use_haiku: bool = False

    # Debug configuration
    debug_agents: bool = False

    # Background scheduler configuration
    max_concurrent_rooms: int = 5

    # Deprecated settings (kept for backwards compatibility warnings)
    enable_recall_tool: Optional[str] = None
    enable_memory_tool: Optional[str] = None

    @field_validator("read_guideline_by", mode="before")
    @classmethod
    def validate_guideline_mode(cls, v: Optional[str]) -> str:
        """Validate and normalize READ_GUIDELINE_BY setting."""
        if not v:
            return "active_tool"
        v_lower = v.lower()
        if v_lower in ("description", "active_tool"):
            return v_lower
        # Invalid value - log warning and default to active_tool
        import logging

        logging.warning(f"Invalid READ_GUIDELINE_BY value: {v}. Defaulting to 'active_tool' mode.")
        return "active_tool"

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

        In bundled mode, returns the working directory (where the exe is located).
        In dev mode, returns the parent of the backend directory.

        Returns:
            Path to the project root directory
        """
        return _get_work_dir()

    @property
    def backend_dir(self) -> Path:
        """
        Get the backend directory.

        In bundled mode, this is the temp extraction directory.
        In dev mode, this is the actual backend directory.

        Returns:
            Path to the backend directory
        """
        if _is_frozen():
            return _get_base_path()
        return Path(__file__).parent.parent

    @property
    def agents_dir(self) -> Path:
        """
        Get the agents configuration directory.

        In bundled mode, agents are in the working directory (copied from bundle on first run).
        In dev mode, agents are in the project root.

        Returns:
            Path to the agents directory
        """
        return _get_work_dir() / "agents"

    @property
    def bundled_agents_dir(self) -> Path | None:
        """
        Get the bundled agents directory (fallback for bundled mode).

        Returns:
            Path to bundled agents directory in frozen mode, None in dev mode
        """
        if _is_frozen():
            return _get_base_path() / "agents"
        return None

    @property
    def config_dir(self) -> Path:
        """
        Get the configuration files directory.

        In bundled mode, config is at the base path (extraction directory).
        In dev mode, config is in backend/config.

        Returns:
            Path to config directory
        """
        if _is_frozen():
            return _get_base_path() / "config"
        return Path(__file__).parent.parent / "config"

    @property
    def tools_config_path(self) -> Path:
        """
        Get the path to tools.yaml configuration file.

        Returns:
            Path to tools.yaml
        """
        return self.config_dir / "tools.yaml"

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
    def guidelines_config_path(self) -> Path:
        """
        Get the path to the guidelines configuration file.

        Returns:
            Path to the guidelines YAML file (e.g., guidelines_3rd.yaml)
        """
        return self.config_dir / f"{self.guidelines_file}.yaml"

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

    def log_deprecation_warnings(self) -> None:
        """Log deprecation warnings for old environment variables."""
        import logging

        logger = logging.getLogger("Settings")

        if self.enable_recall_tool:
            logger.warning(
                "ENABLE_RECALL_TOOL is deprecated and can be removed. "
                "The recall tool is now always enabled."
            )

        if self.enable_memory_tool:
            logger.warning(
                "ENABLE_MEMORY_TOOL is deprecated. Memory recording is available regardless of mode. "
                "See .env.example for details."
            )

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

        # Log deprecation warnings
        _settings.log_deprecation_warnings()

    return _settings


def reset_settings() -> None:
    """
    Reset the settings singleton (useful for testing).
    """
    global _settings
    _settings = None
