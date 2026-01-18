"""
Configuration constants for agent config file parsing.

This module defines default prompts and other constants
used in parsing and building agent configurations.

NOTE: Most constants have been moved to core.settings for centralization.
This module re-exports them for backward compatibility.
"""

# Re-export constants from settings for backward compatibility
from core.settings import (
    DEFAULT_FALLBACK_PROMPT,
)


def get_base_system_prompt(provider: str = "claude") -> str:
    """
    Load the base system prompt from guidelines.yaml.

    Supports multiple system prompt variants via 'active_system_prompt' field:
    - "system_prompt" (default): Standard immersion
    - "system_prompt_sentiment": Sentiment-aware with trait expression guidance
    - "system_prompt_minimal": Streamlined version

    Provider-specific system prompts are supported via 'active_system_prompt_{provider}' field.
    For example, 'active_system_prompt_codex' for Codex provider.

    Character configuration is always appended to the system prompt with markdown headings.

    Args:
        provider: The AI provider name ('claude', 'codex'). Defaults to 'claude'.

    Returns:
        The system prompt template with {agent_name} placeholder
    """
    try:
        from config import get_guidelines_config

        guidelines_config = get_guidelines_config()

        # Check for provider-specific system prompt selector
        # Falls back to default 'active_system_prompt' if provider-specific not found
        if provider and provider != "claude":
            provider_key = f"active_system_prompt_{provider}"
            active_prompt_key = guidelines_config.get(provider_key)
            if active_prompt_key:
                system_prompt = guidelines_config.get(active_prompt_key, "")
                if system_prompt:
                    return system_prompt.strip()
                # Provider-specific key specified but prompt not found, log and fall through
                import logging

                logging.warning(
                    f"System prompt '{active_prompt_key}' for provider '{provider}' not found, falling back to default"
                )

        # Default system prompt selection
        active_prompt_key = guidelines_config.get("active_system_prompt", "system_prompt")
        system_prompt = guidelines_config.get(active_prompt_key, "")

        # If active key not found, try default "system_prompt"
        if not system_prompt and active_prompt_key != "system_prompt":
            import logging

            logging.warning(f"System prompt '{active_prompt_key}' not found, falling back to 'system_prompt'")
            system_prompt = guidelines_config.get("system_prompt", "")

        if system_prompt:
            return system_prompt.strip()
        else:
            import logging

            logging.warning("system_prompt not found in guidelines.yaml, using fallback")
            return DEFAULT_FALLBACK_PROMPT
    except Exception as e:
        # Log and use fallback on any error
        import logging

        logging.error(f"Error loading system prompt from guidelines.yaml: {e}")
        return DEFAULT_FALLBACK_PROMPT
