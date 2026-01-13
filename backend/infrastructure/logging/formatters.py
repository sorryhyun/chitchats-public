"""
Debug utilities for agent message logging and inspection.

This module provides tools for formatting and displaying agent messages
in a human-readable format for debugging purposes.
Formatting options are loaded from YAML configuration.
"""

import json

from core.config import get_debug_config


def format_message_for_debug(message) -> str:
    """Format a message object for readable debug output.

    Formatting options are loaded from debug.yaml configuration.

    Args:
        message: A message object from Claude SDK to format

    Returns:
        JSON-formatted string representation of the message
    """
    # Load formatting options from YAML configuration
    config = get_debug_config()
    formatting = config.get("debug", {}).get("formatting", {})

    truncate_strings = formatting.get("truncate_strings", True)
    max_str_length = formatting.get("max_string_length", 500)
    include_signatures = formatting.get("include_signatures", False)

    def _serialize_value(value):
        """Recursively serialize values for debug output."""
        if isinstance(value, str):
            if truncate_strings and len(value) > max_str_length:
                return value[:max_str_length] + f"... (truncated, total {len(value)} chars)"
            return value
        elif isinstance(value, list):
            # Expand list items
            return [_serialize_value(item) for item in value]
        elif isinstance(value, dict):
            # Expand dict items, optionally skip signature field
            return {k: _serialize_value(v) for k, v in value.items() if include_signatures or k != "signature"}
        elif hasattr(value, "__dict__"):
            # Convert objects to dict, optionally skip signature field
            return {
                "_type": value.__class__.__name__,
                **{
                    k: _serialize_value(v)
                    for k, v in value.__dict__.items()
                    if not k.startswith("_") and (include_signatures or k != "signature")
                },
            }
        else:
            return value

    try:
        # Try to convert to dict for JSON serialization
        if hasattr(message, "__dict__"):
            msg_dict = {"type": message.__class__.__name__, "attributes": {}}
            for key, value in message.__dict__.items():
                if not key.startswith("_"):
                    msg_dict["attributes"][key] = _serialize_value(value)
            return json.dumps(msg_dict, indent=2, ensure_ascii=False, default=str)
        else:
            return str(message)
    except Exception as e:
        return f"<Error formatting message: {e}>"
