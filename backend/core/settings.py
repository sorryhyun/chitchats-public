"""
Centralized application settings using Pydantic BaseSettings.

This module provides type-safe access to environment variables with validation.
All settings are loaded once at application startup.
"""

import socket
import sys
import threading
from pathlib import Path
from typing import List, Optional, Set

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings


def _is_frozen() -> bool:
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _hostname_ips(timeout: float = 0.5) -> Set[str]:
    """Resolve this machine's hostname to LAN IPs, giving up after `timeout`.

    A hostname that doesn't resolve (the norm on macOS, where it is `*.local`, and on
    any host behind a VPN) costs the resolver ~5s before it fails. Doing that inline
    stalled startup, so the lookup runs on a daemon thread we simply stop waiting for.
    """
    ips: Set[str] = set()

    def _resolve() -> None:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ips.add(info[4][0])
        except OSError:
            pass  # Unresolvable hostname: the default-route probe below still finds the LAN IP.

    thread = threading.Thread(target=_resolve, daemon=True)
    thread.start()
    thread.join(timeout)
    return set(ips)  # Copy: the thread may still be running, and we accept losing late results.


def _default_route_ip() -> Optional[str]:
    """LAN IP of the interface holding the default route.

    A UDP `connect` sends no packets — it only consults the routing table — so this is
    instant and works offline. This is what actually finds the LAN IP on most machines.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


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

    # CORS configuration
    frontend_url: Optional[str] = None
    vercel_url: Optional[str] = None

    # Model configuration
    use_sonnet: bool = Field(
        default=False,
        validation_alias=AliasChoices("use_sonnet", "USE_SONNET", "use_haiku", "USE_HAIKU"),
    )

    # Debug configuration
    debug_agents: bool = False

    # Background scheduler configuration
    max_concurrent_rooms: int = 5

    # Codex provider configuration
    codex_model: str = "gpt-5.5"  # Default model for Codex provider

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

    @field_validator("use_sonnet", mode="before")
    @classmethod
    def validate_use_sonnet(cls, v: Optional[str]) -> bool:
        """Parse use_sonnet from string to bool."""
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

        # Add local network IPs so the dev frontend can be opened from another device
        local_ips = _hostname_ips()
        default_route_ip = _default_route_ip()
        if default_route_ip:
            local_ips.add(default_route_ip)

        for local_ip in sorted(local_ips):
            origins.extend([f"http://{local_ip}:5173", f"http://{local_ip}:5174"])

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
