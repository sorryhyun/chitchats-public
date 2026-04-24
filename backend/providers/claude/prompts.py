"""Claude provider prompt accessors (delegates to providers.prompt_builder)."""

from typing import Any, Dict

from providers.prompt_builder import get_base_system_prompt as _get_base_system_prompt
from providers.prompt_builder import load_provider_prompts


def _get_prompts_config() -> Dict[str, Any]:
    return load_provider_prompts("claude")


def get_base_system_prompt() -> str:
    return _get_base_system_prompt("claude")


__all__ = ["get_base_system_prompt", "_get_prompts_config"]
