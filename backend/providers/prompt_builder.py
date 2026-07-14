"""
Prompt builder service for constructing agent system prompts.

Centralizes provider-prompt loading and assembly so per-provider modules
don't have to duplicate identical YAML-loading code.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from i18n.korean import format_with_particles

if TYPE_CHECKING:
    from domain.agent_config import AgentConfigData

logger = logging.getLogger(__name__)

_PROVIDERS_DIR = Path(__file__).parent
_BASE_PROMPT_PATH = _PROVIDERS_DIR / "prompts_base.yaml"
_PROVIDER_PROMPT_PATHS: Dict[str, Path] = {
    "claude": _PROVIDERS_DIR / "claude" / "prompts.yaml",
    "codex": _PROVIDERS_DIR / "codex" / "prompts.yaml",
}
_DEFAULT_PROVIDER = "claude"

# Only these are resolved at load time. {agent_name} and {situation_builder_note}
# are deliberately left in place — they are filled per agent and per room later.
_OVERLAY_KEYS = ("vendor", "model_name", "policy_tool", "provider_sections", "provider_notes")


def _resolve_provider(provider: str) -> str:
    if provider in _PROVIDER_PROMPT_PATHS:
        return provider
    logger.warning(f"Unknown provider '{provider}', falling back to '{_DEFAULT_PROVIDER}'")
    return _DEFAULT_PROVIDER


def load_provider_prompts(provider: str = _DEFAULT_PROVIDER) -> Dict[str, Any]:
    """Load the raw prompts YAML for a given provider."""
    from infrastructure.yaml_cache import get_cached_config

    return get_cached_config(_PROVIDER_PROMPT_PATHS[_resolve_provider(provider)])


def load_base_prompts() -> Dict[str, Any]:
    """Load the shared, provider-agnostic prompts YAML."""
    from infrastructure.yaml_cache import get_cached_config

    return get_cached_config(_BASE_PROMPT_PATH)


def _apply_overlay(template: str, overlay: Dict[str, Any]) -> str:
    """Substitute the provider overlay into the shared base template.

    Uses plain replacement rather than str.format so that the placeholders resolved
    downstream ({agent_name}, {situation_builder_note}) pass through untouched.
    """
    rendered = template
    for key in _OVERLAY_KEYS:
        rendered = rendered.replace("{" + key + "}", str(overlay.get(key, "")).strip())

    # An empty overlay slot leaves a blank line behind; collapse the run it creates.
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered.strip()


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
    """Get the active base system prompt for a provider.

    The body comes from the shared prompts_base.yaml, with the provider's overlay
    substituted in. A provider may still define the active prompt key itself to
    override the shared body wholesale.
    """
    from core.settings import DEFAULT_FALLBACK_PROMPT

    try:
        provider_config = load_provider_prompts(provider)
        base_config = load_base_prompts()

        active_key = provider_config.get("active_system_prompt") or base_config.get(
            "active_system_prompt", "system_prompt_v8"
        )

        # Provider-local override wins; otherwise use the shared base.
        template = provider_config.get(active_key) or base_config.get(active_key)
        if template and isinstance(template, str):
            return _apply_overlay(template, provider_config.get("overlay", {}))

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
    "load_base_prompts",
    "load_provider_prompts",
]
