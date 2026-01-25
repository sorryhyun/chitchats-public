"""
MCP server configuration builder.

This module provides shared utilities for building MCP server configurations
that work across different AI providers (Claude, Codex).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class MCPServerEnv:
    """Environment configuration for MCP servers.

    Attributes:
        agent_name: Name of the agent
        provider: Provider type ("claude" or "codex")
        group_name: Optional agent group name
        agent_id: Optional agent ID (for action server)
        config_file: Optional path to agent config folder
        room_id: Optional room ID (for action server)
        has_situation_builder: Whether room has situation builder (for guidelines)
    """

    agent_name: str
    provider: str
    group_name: Optional[str] = None
    agent_id: Optional[int] = None
    config_file: Optional[str] = None
    room_id: Optional[int] = None
    has_situation_builder: bool = False


# Type alias for MCP server subprocess config
MCPServerConfig = Dict[str, Any]


class MCPConfigBuilder:
    """Builder for MCP server configurations.

    Creates subprocess configurations for MCP servers that communicate via stdio.
    Supports both Claude and Codex providers with consistent environment setup.
    """

    @staticmethod
    def build_all_servers(
        env_config: MCPServerEnv,
        include_etc: bool = True,
        prefer_venv: bool = False,
    ) -> Dict[str, MCPServerConfig]:
        """Build MCP server configurations for all server types.

        Args:
            env_config: Environment configuration for the servers
            include_etc: Whether to include the 'etc' server (Claude uses it, Codex may not)
            prefer_venv: Whether to prefer virtualenv Python (for Codex)

        Returns:
            Dict mapping server names to subprocess configurations
        """
        # Lazy import to avoid circular dependency
        from core import get_settings

        settings = get_settings()
        backend_dir = str(settings.backend_dir)

        # Get Python executable
        python_exe = MCPConfigBuilder._get_python_executable(prefer_venv)

        # Build base environment variables
        base_env = MCPConfigBuilder._build_base_env(env_config, backend_dir)

        # Build action server config
        action_env = MCPConfigBuilder._build_action_env(base_env, env_config)

        # Build guidelines server config
        guidelines_env = MCPConfigBuilder._build_guidelines_env(base_env, env_config)

        # When running as PyInstaller bundle, use --mcp-server flag instead of -m
        is_frozen = getattr(sys, "frozen", False)

        if is_frozen:
            # PyInstaller bundle: use --mcp-server flag that launcher.py understands
            action_args = ["--mcp-server", "action"]
            guidelines_args = ["--mcp-server", "guidelines"]
            etc_args = ["--mcp-server", "etc"]
        else:
            # Development: use Python module invocation
            action_args = ["-m", "mcp_servers.action_server"]
            guidelines_args = ["-m", "mcp_servers.guidelines_server"]
            etc_args = ["-m", "mcp_servers.etc_server"]

        servers: Dict[str, MCPServerConfig] = {
            "action": {
                "command": python_exe,
                "args": action_args,
                "env": action_env,
                "cwd": backend_dir,
            },
            "guidelines": {
                "command": python_exe,
                "args": guidelines_args,
                "env": guidelines_env,
                "cwd": backend_dir,
            },
        }

        # Add etc server if requested (typically for Claude)
        if include_etc:
            servers["etc"] = {
                "command": python_exe,
                "args": etc_args,
                "env": base_env.copy(),
                "cwd": backend_dir,
            }

        return servers

    @staticmethod
    def _get_python_executable(prefer_venv: bool = False) -> str:
        """Get the Python executable path.

        Args:
            prefer_venv: If True, prefer virtualenv Python if available

        Returns:
            Path to Python executable
        """
        if prefer_venv:
            venv_path = os.environ.get("VIRTUAL_ENV")
            if venv_path:
                return str(Path(venv_path) / "bin" / "python")
        return sys.executable

    @staticmethod
    def _build_base_env(env_config: MCPServerEnv, backend_dir: str) -> Dict[str, str]:
        """Build base environment variables shared by all servers."""
        env: Dict[str, str] = {
            "AGENT_NAME": env_config.agent_name,
            "PROVIDER": env_config.provider,
            "PYTHONPATH": backend_dir,
        }
        if env_config.group_name:
            env["AGENT_GROUP"] = env_config.group_name
        return env

    @staticmethod
    def _build_action_env(base_env: Dict[str, str], env_config: MCPServerEnv) -> Dict[str, str]:
        """Build environment variables for the action server."""
        action_env = base_env.copy()
        if env_config.agent_id is not None:
            action_env["AGENT_ID"] = str(env_config.agent_id)
        if env_config.config_file is not None:
            action_env["CONFIG_FILE"] = env_config.config_file
        if env_config.room_id is not None:
            action_env["ROOM_ID"] = str(env_config.room_id)
        return action_env

    @staticmethod
    def _build_guidelines_env(base_env: Dict[str, str], env_config: MCPServerEnv) -> Dict[str, str]:
        """Build environment variables for the guidelines server."""
        guidelines_env = base_env.copy()
        if env_config.has_situation_builder:
            guidelines_env["HAS_SITUATION_BUILDER"] = "true"
        return guidelines_env
