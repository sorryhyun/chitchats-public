"""
Centralized application settings using Pydantic BaseSettings.

This module provides type-safe access to environment variables with validation.
All settings are loaded once at application startup.
"""

from pathlib import Path
from typing import List, Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


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
    memory_by: Literal["RECALL", "BRAIN"] = "RECALL"
    recall_memory_file: str = "consolidated_memory"

    # Guidelines system
    read_guideline_by: Literal["description", "active_tool"] = "active_tool"

    # Model configuration
    use_haiku: bool = False

    # Debug configuration
    debug_agents: bool = False

    # Agent SDK configuration
    agent_cwd: str = "/tmp/claude-empty"
    agent_pool_max_size: int = 50  # Maximum number of concurrent SDK clients
    agent_pool_lock_timeout: float = 30.0  # Seconds to wait for connection lock

    # Background scheduler configuration
    max_concurrent_rooms: int = 5

    # Deprecated settings (kept for backwards compatibility warnings)
    enable_recall_tool: Optional[str] = None
    enable_memory_tool: Optional[str] = None

    @field_validator("memory_by", mode="before")
    @classmethod
    def validate_memory_by(cls, v: Optional[str]) -> str:
        """Validate and normalize MEMORY_BY setting."""
        if not v:
            return "RECALL"
        v_upper = v.upper()
        if v_upper in ("RECALL", "BRAIN"):
            return v_upper
        # Invalid value - log warning and default to RECALL
        import logging

        logging.warning(f"Invalid MEMORY_BY value: {v}. Defaulting to RECALL mode.")
        return "RECALL"

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
                "ENABLE_RECALL_TOOL is deprecated. Please use MEMORY_BY=RECALL instead. "
                "See .env.example for migration guide."
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
        # Find .env file in project root (parent of backend/)
        backend_dir = Path(__file__).parent.parent
        project_root = backend_dir.parent
        env_path = project_root / ".env"

        # Create settings with explicit env file path
        if env_path.exists():
            _settings = Settings(_env_file=str(env_path))
        else:
            _settings = Settings()

        # Log deprecation warnings
        _settings.log_deprecation_warnings()

    return _settings


def reset_settings() -> None:
    """
    Reset the settings singleton (useful for testing).
    """
    global _settings
    _settings = None
