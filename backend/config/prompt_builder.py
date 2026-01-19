"""
Prompt builder service for constructing agent system prompts.

This module provides centralized prompt building logic to avoid duplication
across CRUD operations.
"""

import logging

from domain.agent_config import AgentConfigData
from i18n.korean import format_with_particles

from .constants import get_base_system_prompt

logger = logging.getLogger(__name__)


def config_to_markdown(config_data: AgentConfigData, agent_name: str) -> str:
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

    if config_data.long_term_memory_subtitles:
        sections.append(f"## {agent_name}이 가진 기억 index\n\n{config_data.long_term_memory_subtitles}")

    if sections:
        return "\n\n" + "\n\n".join(sections)
    return ""


def build_system_prompt(agent_name: str, config_data: AgentConfigData, provider: str = "claude") -> str:
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
    # Start with base system prompt and apply Korean particle formatting
    # Pass provider to get provider-specific system prompt if available
    system_prompt = format_with_particles(get_base_system_prompt(provider), agent_name=agent_name)

    # Append character configuration with markdown headings
    config_markdown = config_to_markdown(config_data, agent_name)
    if config_markdown:
        system_prompt += config_markdown

    return system_prompt
