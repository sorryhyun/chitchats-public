"""
Centralized application settings using Pydantic BaseSettings.

This module provides type-safe access to environment variables with validation.
All settings are loaded once at application startup.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


def _is_frozen() -> bool:
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _get_base_path() -> Path:
    """Get the base path for bundled resources (config files, static files)."""
    if _is_frozen():
        # Running as PyInstaller bundle - resources are in temp extraction dir
        return Path(sys._MEIPASS)
    else:
        # Running in development - relative to this file
        return Path(__file__).parent.parent.parent


def _get_work_dir() -> Path:
    """Get the working directory for user data (.env, agents, etc.)."""
    if _is_frozen():
        # Running as PyInstaller bundle - user data next to exe
        return Path(sys.executable).parent
    else:
        # Running in development - project root
        return Path(__file__).parent.parent.parent


# ============================================================================
# Application Constants
# ============================================================================

# Bundled Codex binary paths by platform (relative to project root)
BUNDLED_CODEX_PATHS: Dict[str, str] = {
    "windows-amd64": "bundled/codex-x86_64-pc-windows-msvc.exe",
    "windows-x86_64": "bundled/codex-x86_64-pc-windows-msvc.exe",
    "darwin-arm64": "bundled/codex-aarch64-apple-darwin",
    "darwin-x86_64": "bundled/codex-x86_64-apple-darwin",
    "linux-x86_64": "bundled/codex-x86_64-unknown-linux-gnu",
    "linux-aarch64": "bundled/codex-aarch64-unknown-linux-gnu",
}

# Default fallback prompt if no configuration is provided
DEFAULT_FALLBACK_PROMPT = "You are a helpful AI assistant."

# Skip message text (displayed when agent chooses not to respond)
SKIP_MESSAGE_TEXT = "(무시함)"


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

    # Background scheduler configuration
    max_concurrent_rooms: int = 5

    # Codex provider configuration
    codex_model: str = "gpt-5.2"  # Default model for Codex provider

    # Custom OpenAI-compatible provider configuration
    custom_api_key: Optional[str] = None  # API key for custom provider
    custom_base_url: Optional[str] = None  # Base URL for custom provider (e.g., https://api.example.com/v1)
    custom_model: str = "gpt-4"  # Model for custom provider (set via CUSTOM_MODEL env var)
    enable_custom_provider: bool = False  # Feature flag to enable custom provider

    # Voice server configuration
    voice_server_url: str = "http://localhost:8002"  # Voice TTS server URL

    # Tool toggles
    enable_excuse: bool = True  # Enable excuse tool for agents
    enable_community: bool = False  # Enable community social tools (Moltbook)

    # Moltbook API configuration
    moltbook_api_key: Optional[str] = None  # API key for Moltbook social network

    # Memory preview configuration
    memory_preview_with_thoughts: bool = False  # Show thoughts in recall tool preview

    # Google OAuth configuration
    google_client_id: Optional[str] = None  # Google OAuth Client ID for Sign-In

    # Proxy configuration for rate limiting
    trusted_proxy_count: int = 0  # Number of trusted proxies (for X-Forwarded-For handling)

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

    @field_validator("memory_preview_with_thoughts", mode="before")
    @classmethod
    def validate_memory_preview_with_thoughts(cls, v: Optional[str]) -> bool:
        """Parse memory_preview_with_thoughts from string to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() == "true"
        return False

    @field_validator("enable_custom_provider", mode="before")
    @classmethod
    def validate_enable_custom_provider(cls, v: Optional[str]) -> bool:
        """Parse enable_custom_provider from string to bool."""
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
        Get the project root directory.

        In bundled mode: returns base path (temp extraction dir) for bundled resources
        In dev mode: returns parent of backend/

        Returns:
            Path to the project root directory
        """
        return _get_base_path()

    @property
    def work_dir(self) -> Path:
        """
        Get the working directory for user data (.env, agents, etc.).

        In bundled mode: directory containing the exe
        In dev mode: project root

        Returns:
            Path to the working directory
        """
        return _get_work_dir()

    @property
    def backend_dir(self) -> Path:
        """
        Get the backend directory for bundled resources.

        In bundled mode: same as base path (modules at root of extraction)
        In dev mode: project_root/backend

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

        Agents are user data, so they live in work_dir (next to exe in bundled mode).

        Returns:
            Path to the agents directory
        """
        return self.work_dir / "agents"

    @property
    def config_dir(self) -> Path:
        """
        Get the general configuration files directory.

        Returns:
            Path to config directory (for debug.yaml, conversation_context.yaml)
        """
        if _is_frozen():
            return _get_base_path() / "config"
        return self.backend_dir / "config"

    @property
    def mcp_servers_config_dir(self) -> Path:
        """
        Get the MCP servers configuration directory.

        Returns:
            Path to mcp_servers/config directory (for tools.py, guidelines)
        """
        if _is_frozen():
            return _get_base_path() / "mcp_servers" / "config"
        return self.backend_dir / "mcp_servers" / "config"

    @property
    def debug_config_path(self) -> Path:
        """
        Get the path to debug.yaml configuration file.

        Returns:
            Path to debug.yaml
        """
        return self.mcp_servers_config_dir / "debug.yaml"

    @property
    def conversation_context_config_path(self) -> Path:
        """
        Get the path to the legacy conversation_context.yaml configuration file.

        DEPRECATED: Conversation context is now loaded from:
        - Shared config: config/prompts_shared.yaml
        - Provider-specific: providers/{provider}/prompts.yaml

        This property is kept for backward compatibility.

        Returns:
            Path to conversation_context.yaml in backend/config/ (may not exist)
        """
        return self.config_dir / "conversation_context.yaml"

    @property
    def system_prompt_config_path(self) -> Path:
        """
        Get the path to the legacy system prompt configuration file.

        DEPRECATED: System prompts are now stored in providers/{provider}/prompts.yaml.
        This property is kept for backward compatibility.

        Returns:
            Path to system_prompt.yaml in backend/config/ (may not exist)
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

        # Add local network IPs for development (including WSL2)
        import socket

        try:
            # Get all IPs from all network interfaces
            local_ips = set()
            hostname = socket.gethostname()
            # Try hostname-based lookup
            try:
                local_ips.add(socket.gethostbyname(hostname))
            except Exception:
                pass
            # Try getting all addresses for the hostname
            try:
                for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    local_ips.add(info[4][0])
            except Exception:
                pass
            # Try connecting to external to find default route IP (works in WSL2)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    local_ips.add(s.getsockname()[0])
            except Exception:
                pass
            for local_ip in local_ips:
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

        # Find .env file in work directory (next to exe in bundled mode)
        env_path = _settings.work_dir / ".env"

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
