"""
MCP config generation for Codex CLI.

This module generates -c override arguments for Codex CLI to configure
MCP servers at runtime without modifying ~/.codex/config.toml.

Usage:
    overrides = build_mcp_overrides(agent_name="루카", ...)
    # Returns list like:
    # ['mcp_servers.chitchats_action.command="/path/to/python"', ...]

Bundled Mode:
    When running as a PyInstaller bundle, the exe spawns itself with --mcp flag
    instead of using Python module execution:
    - ClaudeCodeRP.exe --mcp action
    - ClaudeCodeRP.exe --mcp guidelines
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("CodexMCPConfig")


def build_mcp_overrides(
    agent_name: str,
    agent_group: str,
    backend_path: str,
    work_dir: str,
    room_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    config_file: Optional[str] = None,
) -> List[str]:
    """Build Codex -c override arguments for MCP server configuration.

    Creates a list of -c override strings that configure MCP servers
    at runtime without touching ~/.codex/config.toml.

    Args:
        agent_name: Name of the agent (passed to MCP servers via env)
        agent_group: Group name for tool config overrides
        backend_path: Absolute path to the backend directory
        work_dir: Working directory where agents folder lives (exe location in bundled mode)
        room_id: Optional room ID for context
        agent_id: Optional agent ID for context
        config_file: Optional path to agent config directory (for loading memories)

    Returns:
        List of -c override strings for Codex CLI

    Example:
        overrides = build_mcp_overrides("루카", "렌탈여친", "/path/to/backend", "/path/to/work")
        # Use with: codex exec -c <override1> -c <override2> ... "prompt"
    """
    overrides = []

    # Check if running as bundled PyInstaller exe
    is_bundled = getattr(sys, "frozen", False)

    if is_bundled:
        # In bundled mode, spawn the exe itself with --mcp flag
        command = sys.executable
        action_args = '["--mcp", "action"]'
        guidelines_args = '["--mcp", "guidelines"]'
    else:
        # In development mode, use Python module execution
        python_path = os.environ.get("VIRTUAL_ENV")
        if python_path:
            command = str(Path(python_path) / "bin" / "python")
        else:
            command = "python"
        action_args = '["-m", "mcp_servers.action_server"]'
        guidelines_args = '["-m", "mcp_servers.guidelines_server"]'

    # Build action server overrides
    action_prefix = "mcp_servers.action"
    overrides.append(f'{action_prefix}.command="{command}"')
    overrides.append(f'{action_prefix}.args={action_args}')
    overrides.append(f'{action_prefix}.cwd="{backend_path}"')
    overrides.append(f'{action_prefix}.env.AGENT_NAME="{agent_name}"')
    overrides.append(f'{action_prefix}.env.AGENT_GROUP="{agent_group}"')
    overrides.append(f'{action_prefix}.env.PYTHONPATH="{backend_path}"')
    overrides.append(f'{action_prefix}.env.WORK_DIR="{work_dir}"')
    overrides.append(f'{action_prefix}.env.PROVIDER="codex"')

    if room_id is not None:
        overrides.append(f'{action_prefix}.env.ROOM_ID="{room_id}"')
    if agent_id is not None:
        overrides.append(f'{action_prefix}.env.AGENT_ID="{agent_id}"')
    if config_file is not None:
        overrides.append(f'{action_prefix}.env.CONFIG_FILE="{config_file}"')

    # Build guidelines server overrides
    guidelines_prefix = "mcp_servers.guidelines"
    overrides.append(f'{guidelines_prefix}.command="{command}"')
    overrides.append(f'{guidelines_prefix}.args={guidelines_args}')
    overrides.append(f'{guidelines_prefix}.cwd="{backend_path}"')
    overrides.append(f'{guidelines_prefix}.env.AGENT_NAME="{agent_name}"')
    overrides.append(f'{guidelines_prefix}.env.PYTHONPATH="{backend_path}"')
    overrides.append(f'{guidelines_prefix}.env.WORK_DIR="{work_dir}"')
    overrides.append(f'{guidelines_prefix}.env.PROVIDER="codex"')

    logger.debug(f"Built {len(overrides)} MCP config overrides for agent {agent_name}")
    return overrides
