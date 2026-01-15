"""
MCP config generation for Codex CLI.

This module generates -c override arguments for Codex CLI to configure
MCP servers at runtime without modifying ~/.codex/config.toml.

Usage:
    overrides = build_mcp_overrides(agent_name="루카", ...)
    # Returns list like:
    # ['mcp_servers.chitchats_action.command="/path/to/python"', ...]
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("CodexMCPConfig")


def build_mcp_overrides(
    agent_name: str,
    agent_group: str,
    backend_path: str,
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
        room_id: Optional room ID for context
        agent_id: Optional agent ID for context
        config_file: Optional path to agent config directory (for loading memories)

    Returns:
        List of -c override strings for Codex CLI

    Example:
        overrides = build_mcp_overrides("루카", "렌탈여친", "/path/to/backend")
        # Use with: codex exec -c <override1> -c <override2> ... "prompt"
    """
    overrides = []

    # Get Python executable path
    python_path = os.environ.get("VIRTUAL_ENV")
    if python_path:
        python_exe = str(Path(python_path) / "bin" / "python")
    else:
        python_exe = "python"

    # Build action server overrides
    action_prefix = "mcp_servers.chitchats_action"
    overrides.append(f'{action_prefix}.command="{python_exe}"')
    overrides.append(f'{action_prefix}.args=["-m", "mcp_servers.action_server"]')
    overrides.append(f'{action_prefix}.cwd="{backend_path}"')
    overrides.append(f'{action_prefix}.env.AGENT_NAME="{agent_name}"')
    overrides.append(f'{action_prefix}.env.AGENT_GROUP="{agent_group}"')
    overrides.append(f'{action_prefix}.env.PYTHONPATH="{backend_path}"')
    overrides.append(f'{action_prefix}.env.PROVIDER="codex"')

    if room_id is not None:
        overrides.append(f'{action_prefix}.env.ROOM_ID="{room_id}"')
    if agent_id is not None:
        overrides.append(f'{action_prefix}.env.AGENT_ID="{agent_id}"')
    if config_file is not None:
        overrides.append(f'{action_prefix}.env.CONFIG_FILE="{config_file}"')

    # Build guidelines server overrides
    guidelines_prefix = "mcp_servers.chitchats_guidelines"
    overrides.append(f'{guidelines_prefix}.command="{python_exe}"')
    overrides.append(f'{guidelines_prefix}.args=["-m", "mcp_servers.guidelines_server"]')
    overrides.append(f'{guidelines_prefix}.cwd="{backend_path}"')
    overrides.append(f'{guidelines_prefix}.env.AGENT_NAME="{agent_name}"')
    overrides.append(f'{guidelines_prefix}.env.PYTHONPATH="{backend_path}"')
    overrides.append(f'{guidelines_prefix}.env.PROVIDER="codex"')

    logger.debug(f"Built {len(overrides)} MCP config overrides for agent {agent_name}")
    return overrides
