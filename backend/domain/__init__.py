"""
Domain layer for internal business logic data structures.

This package contains dataclasses used for clean parameter passing
between functions in the business logic layer.

Note: Input models (SkipInput, MemorizeInput, RecallInput, etc.) have been
moved to mcp_servers.config.tools. Import them from there or from mcp_servers.config.
"""

from .agent_config import AgentConfigData
from .contexts import (
    AgentMessageData,
    AgentResponseContext,
    MessageContext,
    OrchestrationContext,
)
from .enums import ParticipantType

__all__ = [
    "AgentConfigData",
    "AgentResponseContext",
    "OrchestrationContext",
    "MessageContext",
    "AgentMessageData",
    "ParticipantType",
]
