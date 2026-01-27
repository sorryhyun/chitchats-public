"""
Codex provider prompt configuration.

This module provides functions to load Codex-specific prompts from prompts.yaml.
"""

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Path to this provider's prompts.yaml
_PROMPTS_PATH = Path(__file__).parent / "prompts.yaml"


def _get_prompts_config() -> Dict[str, Any]:
    """Load the prompts configuration from prompts.yaml."""
    from infrastructure.yaml_cache import get_cached_config

    return get_cached_config(_PROMPTS_PATH)


def get_base_system_prompt() -> str:
    """
    Get the base system prompt for Codex provider.

    Returns:
        The system prompt template with {agent_name} placeholder
    """
    from core.settings import DEFAULT_FALLBACK_PROMPT

    try:
        config = _get_prompts_config()

        # Get active prompt key
        active_prompt_key = config.get("active_system_prompt", "system_prompt_v7")

        # Get the prompt content
        system_prompt = config.get(active_prompt_key)

        if system_prompt and isinstance(system_prompt, str):
            return system_prompt.strip()

        logger.warning(f"System prompt '{active_prompt_key}' not found for Codex provider, using fallback")
        return DEFAULT_FALLBACK_PROMPT

    except Exception as e:
        logger.error(f"Error loading Codex system prompt: {e}")
        return DEFAULT_FALLBACK_PROMPT


__all__ = [
    "get_base_system_prompt",
]
