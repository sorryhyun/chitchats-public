"""
Prompt builder service for constructing agent system prompts.

Centralizes provider-prompt loading and assembly so per-provider modules
don't have to duplicate identical YAML-loading code.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from i18n.korean import format_with_particles

if TYPE_CHECKING:
    from domain.agent_config import AgentConfigData

logger = logging.getLogger(__name__)

_PROVIDERS_DIR = Path(__file__).parent
_PROVIDER_PROMPT_PATHS: Dict[str, Path] = {
    "claude": _PROVIDERS_DIR / "claude" / "prompts.yaml",
    "codex": _PROVIDERS_DIR / "codex" / "prompts.yaml",
}
_DEFAULT_PROVIDER = "claude"


def _resolve_provider(provider: str) -> str:
    if provider in _PROVIDER_PROMPT_PATHS:
        return provider
    logger.warning(f"Unknown provider '{provider}', falling back to '{_DEFAULT_PROVIDER}'")
    return _DEFAULT_PROVIDER


def load_provider_prompts(provider: str = _DEFAULT_PROVIDER) -> Dict[str, Any]:
    """Load the raw prompts YAML for a given provider."""
    from infrastructure.yaml_cache import get_cached_config

    return get_cached_config(_PROVIDER_PROMPT_PATHS[_resolve_provider(provider)])


def config_to_markdown(config_data: "AgentConfigData", agent_name: str) -> str:
    """Convert agent configuration to markdown for system prompt injection."""
    sections = []

    if config_data.in_a_nutshell:
        sections.append(f"## {agent_name} in a nutshell\n\n{config_data.in_a_nutshell}")

    if config_data.characteristics:
        sections.append(f"## {agent_name}'s characteristics\n\n{config_data.characteristics}")

    if config_data.recent_events:
        sections.append(f"## Recent events\n\n{config_data.recent_events}")

    if sections:
        return "\n\n" + "\n\n".join(sections)
    return ""


def get_base_system_prompt(provider: str = _DEFAULT_PROVIDER) -> str:
    """Get the active base system prompt for a provider."""
    from core.settings import DEFAULT_FALLBACK_PROMPT

    try:
        config = load_provider_prompts(provider)
        active_key = config.get("active_system_prompt", "system_prompt_v7")
        prompt = config.get(active_key)
        if prompt and isinstance(prompt, str):
            return prompt.strip()
        logger.warning(f"System prompt '{active_key}' not found for provider '{provider}', using fallback")
        return DEFAULT_FALLBACK_PROMPT
    except Exception as e:
        logger.error(f"Error loading system prompt for provider '{provider}': {e}")
        return DEFAULT_FALLBACK_PROMPT


def build_system_prompt(agent_name: str, config_data: "AgentConfigData", provider: str = _DEFAULT_PROVIDER) -> str:
    """Build a complete system prompt for an agent."""
    base_prompt = get_base_system_prompt(provider)
    system_prompt = format_with_particles(base_prompt, agent_name=agent_name)

    config_markdown = config_to_markdown(config_data, agent_name)
    if config_markdown:
        system_prompt += config_markdown

    return system_prompt


__all__ = [
    "build_system_prompt",
    "config_to_markdown",
    "get_base_system_prompt",
    "load_provider_prompts",
]
