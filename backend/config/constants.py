"""
Configuration constants for agent config file parsing.

This module provides the get_base_system_prompt function for loading
system prompts from configuration files.
"""

from core.settings import DEFAULT_FALLBACK_PROMPT


def get_base_system_prompt(provider: str = "claude") -> str:
    """
    Load the base system prompt from system_prompt.yaml.

    The config structure is:
        active_system_prompt: "prompt_name"
        prompt_name:
          claude: |
            ...claude-specific prompt...
          codex: |
            ...codex-specific prompt...

    Args:
        provider: The AI provider ("claude" or "codex")

    Returns:
        The system prompt template with {agent_name} placeholder
    """
    import logging

    try:
        from mcp_servers.config.loaders import get_system_prompt_config

        system_prompt_config = get_system_prompt_config()

        # Get active prompt key (e.g., "system_prompt_operatorsv6")
        active_prompt_key = system_prompt_config.get("active_system_prompt", "system_prompt")

        # Get the prompt config (should be a dict with provider keys)
        prompt_config = system_prompt_config.get(active_prompt_key)

        if prompt_config is None:
            logging.warning(f"System prompt '{active_prompt_key}' not found, using fallback")
            return DEFAULT_FALLBACK_PROMPT

        # Handle nested provider structure
        if isinstance(prompt_config, dict):
            # Try provider-specific prompt, fall back to 'claude'
            system_prompt = prompt_config.get(provider) or prompt_config.get("claude", "")
        else:
            # Legacy: direct string value (backward compatibility)
            system_prompt = prompt_config

        if system_prompt:
            return system_prompt.strip()
        else:
            logging.warning(f"No prompt found for provider '{provider}' in '{active_prompt_key}', using fallback")
            return DEFAULT_FALLBACK_PROMPT

    except Exception as e:
        import logging

        logging.error(f"Error loading system prompt from system_prompt.yaml: {e}")
        return DEFAULT_FALLBACK_PROMPT
