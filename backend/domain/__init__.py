"""
Domain layer for internal business logic data structures.

This package contains dataclasses used for clean parameter passing
between functions in the business logic layer.
"""

from .action_models import (
    MemorizeOutput,
    RecallOutput,
    SkipOutput,
    ToolResponse,
)
from .agent_config import AgentConfigData
from .contexts import (
    AgentMessageData,
    AgentResponseContext,
    MessageContext,
    OrchestrationContext,
)
from .streaming import (
    ContentDeltaEvent,
    ResponseAccumulator,
    StreamEndEvent,
    StreamEvent,
    StreamStartEvent,
    ThinkingDeltaEvent,
)
from .enums import ParticipantType

# Re-export input models from mcp_servers.config.tools (canonical location)
from mcp_servers.config.tools import (
    CurrentTimeInput,
    GuidelinesAnthropicInput,
    GuidelinesReadInput,
    MemorizeInput,
    RecallInput,
    SkipInput,
)

__all__ = [
    "AgentConfigData",
    "AgentResponseContext",
    "OrchestrationContext",
    "MessageContext",
    "AgentMessageData",
    "ParticipantType",
    # Input models (re-exported from mcp_servers.config.tools)
    "SkipInput",
    "MemorizeInput",
    "RecallInput",
    "CurrentTimeInput",
    "GuidelinesReadInput",
    "GuidelinesAnthropicInput",
    # Output models (still in domain)
    "SkipOutput",
    "MemorizeOutput",
    "RecallOutput",
    "ToolResponse",
    # Streaming types
    "StreamStartEvent",
    "ContentDeltaEvent",
    "ThinkingDeltaEvent",
    "StreamEndEvent",
    "StreamEvent",
    "ResponseAccumulator",
]
