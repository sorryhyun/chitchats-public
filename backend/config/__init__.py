"""
Agent configuration module for parsing agent config files.

This module provides functionality to parse agent configuration files from
markdown and manage configuration constants. Agent-specific configuration is
now injected through MCP tool descriptions (see agents/tools.py).
"""

from .agent_io import AgentConfigIO
from .constants import (
    DEFAULT_FALLBACK_PROMPT,
    get_base_system_prompt,
)
from .parser import list_available_configs, parse_agent_config
from .prompt_builder import build_system_prompt

__all__ = [
    "parse_agent_config",
    "list_available_configs",
    "get_base_system_prompt",
    "DEFAULT_FALLBACK_PROMPT",
    "build_system_prompt",
    "AgentConfigIO",
]
