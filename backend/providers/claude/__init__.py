"""
Claude Code provider implementation.

This module provides the Claude Code provider that wraps the Claude Agent SDK
for use with the ChitChats multi-provider abstraction layer.
"""

# Monkey-patch the SDK's message parser to handle rate_limit_event gracefully.
# The SDK raises MessageParseError for unknown message types like rate_limit_event,
# which kills the entire response stream. This patch converts them to SystemMessage instead.
import claude_agent_sdk._internal.client as _cl  # noqa: E402
import claude_agent_sdk._internal.message_parser as _mp  # noqa: E402
from claude_agent_sdk.types import SystemMessage as _SystemMessage  # noqa: E402

_original_parse_message = _mp.parse_message


def _patched_parse_message(data):
    if isinstance(data, dict) and data.get("type") == "rate_limit_event":
        return _SystemMessage(subtype="rate_limit", data=data)
    return _original_parse_message(data)


_mp.parse_message = _patched_parse_message
_cl.parse_message = _patched_parse_message  # type: ignore[attr-defined]  # Patch the already-imported reference

from .client import ClaudeClient
from .parser import ClaudeStreamParser
from .provider import ClaudeClientPool, ClaudeProvider

__all__ = [
    "ClaudeClient",
    "ClaudeClientPool",
    "ClaudeProvider",
    "ClaudeStreamParser",
]
