"""
Prompt builder service for constructing agent system prompts.

This module provides centralized prompt building logic to avoid duplication
across CRUD operations. It dispatches to provider-specific prompt builders.
"""

import logging
from typing import TYPE_CHECKING

from i18n.korean import format_with_particles

if TYPE_CHECKING:
    from domain.agent_config import AgentConfigData

logger = logging.getLogger(__name__)


def config_to_markdown(config_data: "AgentConfigData", agent_name: str) -> str:
    """
    Convert agent configuration to markdown format for system prompt injection.

    Args:
        config_data: Agent configuration data
        agent_name: The name of the agent

    Returns:
        Markdown-formatted configuration string with ## headings
    """
    sections = []

    if config_data.in_a_nutshell:
        sections.append(f"## {agent_name} in a nutshell\n\n{config_data.in_a_nutshell}")

    if config_data.characteristics:
        sections.append(f"## {agent_name}'s characteristics\n\n{config_data.characteristics}")

    if config_data.recent_events:
        sections.append(f"## Recent events\n\n{config_data.recent_events}")

    # Note: Memory subtitles are no longer added to system prompt.
    # They are shown in the recall tool description with thoughts previews.

    if sections:
        return "\n\n" + "\n\n".join(sections)
    return ""


def get_base_system_prompt(provider: str = "claude") -> str:
    """
    Get the base system prompt for a provider.

    Args:
        provider: The AI provider ("claude" or "codex")

    Returns:
        The system prompt template with {agent_name} placeholder
    """
    if provider == "codex":
        from providers.codex.prompts import get_base_system_prompt as codex_prompt

        return codex_prompt()
    else:
        from providers.claude.prompts import get_base_system_prompt as claude_prompt

        return claude_prompt()


def build_system_prompt(agent_name: str, config_data: "AgentConfigData", provider: str = "claude") -> str:
    """
    Build a complete system prompt for an agent.

    This function combines the base system prompt with agent-specific
    configuration markdown, applying Korean particle formatting.

    Args:
        agent_name: The name of the agent
        config_data: Agent configuration data
        provider: The AI provider ("claude" or "codex")

    Returns:
        Complete system prompt string with markdown formatting
    """
    # Get provider-specific base system prompt and apply Korean particle formatting
    base_prompt = get_base_system_prompt(provider)
    system_prompt = format_with_particles(base_prompt, agent_name=agent_name)

    # Append character configuration with markdown headings
    config_markdown = config_to_markdown(config_data, agent_name)
    if config_markdown:
        system_prompt += config_markdown

    return system_prompt


__all__ = [
    "build_system_prompt",
    "config_to_markdown",
    "get_base_system_prompt",
]
