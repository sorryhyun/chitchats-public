"""
Configuration constants for agent config file parsing.

This module defines default prompts and other constants
used in parsing and building agent configurations.

NOTE: Most constants have been moved to core.settings for centralization.
This module re-exports them for backward compatibility.
"""

# Re-export constants from settings for backward compatibility
from core.settings import (
    AGENT_TOOL_NAMES,
    AGENT_TOOL_NAMES_BY_GROUP,
    # BUILTIN_TOOLS,
    DEFAULT_FALLBACK_PROMPT,
    SKIP_MESSAGE_TEXT,
)


def get_base_system_prompt() -> str:
    """
    Load the base system prompt from guidelines.yaml.

    Supports multiple system prompt variants via 'active_system_prompt' field:
    - "system_prompt" (default): Standard immersion
    - "system_prompt_sentiment": Sentiment-aware with trait expression guidance
    - "system_prompt_minimal": Streamlined version

    Character configuration is always appended to the system prompt with markdown headings.

    Returns:
        The system prompt template with {agent_name} placeholder
    """
    try:
        from core.config import get_guidelines_config

        guidelines_config = get_guidelines_config()

        # Check for active_system_prompt selector (for guidelines_v2.yaml)
        # Falls back to "system_prompt" if not specified
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
