"""
Abstract base classes for AI provider implementations.

This module defines the provider abstraction layer that allows ChitChats
to support multiple AI backends (Claude Code, Codex, etc.) with a unified interface.

Architecture:
    AIProvider: Main entry point for provider operations
    AIClient: Individual client connection for message exchange
    AIClientOptions: Configuration for client creation
    AIMessage: Unified message format across providers
    AIStreamEvent: Streaming event for real-time responses
    ParsedStreamMessage: Parsed result from stream messages
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Union

if TYPE_CHECKING:
    from domain.contexts import AgentResponseContext


class ProviderType(str, Enum):
    """Supported AI provider types."""

    CLAUDE = "claude"
    CODEX = "codex"
    CUSTOM = "custom"


@dataclass
class AIMessage:
    """Unified message format across providers.

    Attributes:
        type: Message type (text, thinking, tool_use, system, error)
        content: The message content
        metadata: Provider-specific data (e.g., tool_name, tool_input)
    """

    type: str  # "text", "thinking", "tool_use", "system", "error"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIStreamEvent:
    """Unified streaming event for real-time responses.

    Attributes:
        type: Event type (stream_start, content_delta, thinking_delta, stream_end)
        delta: Incremental content for delta events
        session_id: Session/thread ID for resume support
        metadata: Provider-specific event data
    """

    type: str  # "stream_start", "content_delta", "thinking_delta", "stream_end"
    delta: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedStreamMessage:
    """Structured result from parsing provider stream messages.

    This is the unified output format that all provider parsers must produce.

    Attributes:
        response_text: Accumulated response text
        thinking_text: Accumulated thinking text
        session_id: Session/thread ID if found in this message
        skip_used: True if skip tool was called
        memory_entries: New memory entries from memorize tool
        anthropic_calls: Arguments from anthropic tool calls
    """

    response_text: str
    thinking_text: str
    session_id: Optional[str] = None
    skip_used: bool = False
    memory_entries: List[str] = field(default_factory=list)
    anthropic_calls: List[str] = field(default_factory=list)
    excuse_reasons: List[str] = field(default_factory=list)

    @property
    def has_tool_usage(self) -> bool:
        """Check if any tools were used in this message."""
        return self.skip_used or bool(self.memory_entries) or bool(self.anthropic_calls)


@dataclass
class AIClientOptions:
    """Configuration options for AI client creation.

    This is the provider-agnostic configuration that gets translated
    to provider-specific options by each implementation.

    Attributes:
        system_prompt: The system prompt defining agent behavior
        model: Model identifier (provider-specific interpretation)
        session_id: Optional session ID for conversation resume
        mcp_tools: MCP tool definitions
        max_thinking_tokens: Maximum tokens for thinking/reasoning
        agent_name: Name of the agent (for tool context)
        agent_id: Unique agent identifier
        config_file: Path to agent configuration folder
        group_name: Optional group name for tool config overrides
        has_situation_builder: Whether room has situation builder
        long_term_memory_index: Memory subtitles to content mapping
        working_dir: Working directory for subprocess
        extra_options: Provider-specific additional options
    """

    system_prompt: str
    model: str
    session_id: Optional[str] = None
    mcp_tools: Dict[str, Any] = field(default_factory=dict)
    max_thinking_tokens: int = 32768
    agent_name: str = ""
    agent_id: int = 0
    config_file: Optional[str] = None
    group_name: Optional[str] = None
    has_situation_builder: bool = False
    long_term_memory_index: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    extra_options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(
        cls,
        context: AgentResponseContext,
        system_prompt: str,
        provider_type: ProviderType = ProviderType.CLAUDE,
    ) -> AIClientOptions:
        """Create AIClientOptions from an AgentResponseContext.

        Args:
            context: The agent response context containing agent/room info
            system_prompt: The final system prompt (with timestamp if applicable)
            provider_type: The AI provider type (determines model selection)

        Returns:
            Configured AIClientOptions instance
        """
        # Determine model: use room's model override, then provider default
        from core import get_settings

        settings = get_settings()
        model = context.model or ""
        if not model and provider_type == ProviderType.CODEX and settings.codex_model:
            model = settings.codex_model

        return cls(
            system_prompt=system_prompt,
            model=model,
            session_id=context.session_id,
            agent_name=context.agent_name,
            agent_id=context.agent_id,
            config_file=context.config.config_file,
            group_name=context.group_name,
            has_situation_builder=context.has_situation_builder,
            long_term_memory_index=context.config.long_term_memory_index,
            mcp_tools={
                "agent_name": context.agent_name,
                "agent_group": context.group_name or "default",
                "agent_id": context.agent_id,
                "room_id": context.room_id,
                "config_file": context.config.config_file,
            },
        )


class AIStreamParser(ABC):
    """Abstract parser for provider streaming messages.

    Each provider implementation must create a parser that converts
    provider-specific message formats to the unified ParsedStreamMessage.
    """

    @staticmethod
    @abstractmethod
    def parse_message(
        message: Any,
        current_response: str,
        current_thinking: str,
    ) -> ParsedStreamMessage:
        """Parse a streaming message from the provider.

        Args:
            message: Provider-specific message object
            current_response: Accumulated response text so far
            current_thinking: Accumulated thinking text so far

        Returns:
            ParsedStreamMessage with extracted fields and updated accumulated text
        """
        ...


class AIClient(ABC):
    """Abstract AI client interface for individual connections.

    Each provider implements this interface to handle the actual
    communication with the AI backend.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the connection to the AI backend."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        ...

    @abstractmethod
    async def query(self, message: Union[str, AsyncIterator[dict]]) -> None:
        """Send a message/query to the AI backend.

        Args:
            message: The message content - can be a string or async iterator
                    of content blocks for multimodal support
        """
        ...

    @abstractmethod
    def receive_response(self) -> AsyncIterator[Any]:
        """Receive streaming response from the AI backend.

        This is an async generator method that yields provider-specific
        message objects. Implementations should use `async for` to iterate.

        Yields:
            Provider-specific message objects that should be parsed
            using the corresponding AIStreamParser
        """
        ...

    @abstractmethod
    async def interrupt(self) -> None:
        """Interrupt the current response generation."""
        ...

    @property
    @abstractmethod
    def session_id(self) -> Optional[str]:
        """Get the current session/thread ID for resume support."""
        ...

    @property
    @abstractmethod
    def options(self) -> Any:
        """Get the provider-specific options object."""
        ...

    @options.setter
    @abstractmethod
    def options(self, value: Any) -> None:
        """Update the provider-specific options object."""
        ...


class ClientPoolInterface(ABC):
    """Abstract interface for AI client pooling.

    Each provider can implement this interface to manage client lifecycle
    with provider-specific connection logic. The interface defines common
    pooling operations that work across all providers.
    """

    @abstractmethod
    async def get_or_create(
        self,
        task_id: Any,
        options: Any,
    ) -> tuple[AIClient, bool]:
        """Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task (provider-agnostic)
            options: Provider-specific client options

        Returns:
            (client, is_new) tuple:
            - client: AIClient implementation
            - is_new: True if newly created, False if reused from pool
        """
        ...

    @abstractmethod
    async def cleanup(self, task_id: Any) -> None:
        """Remove and cleanup a specific client.

        Args:
            task_id: Identifier for the client to cleanup
        """
        ...

    @abstractmethod
    async def cleanup_room(self, room_id: int) -> None:
        """Cleanup all clients for a specific room.

        Args:
            room_id: Room ID to cleanup
        """
        ...

    @abstractmethod
    async def shutdown_all(self) -> None:
        """Graceful shutdown of all clients."""
        ...

    @abstractmethod
    def get_keys_for_agent(self, agent_id: int) -> list[Any]:
        """Get all pool keys for a specific agent.

        Args:
            agent_id: Agent ID to filter

        Returns:
            List of task identifiers for this agent
        """
        ...

    @abstractmethod
    def keys(self) -> Any:
        """Get all pool keys.

        Returns:
            Iterable of all task identifiers in the pool
        """
        ...

    @property
    @abstractmethod
    def pool(self) -> dict:
        """Get the underlying pool dictionary.

        Returns:
            Dict mapping task identifiers to clients
        """
        ...


class AIProvider(ABC):
    """Abstract provider interface - factory for clients and configuration.

    This is the main entry point for provider operations. Each provider
    implementation creates this to manage client lifecycle.
    """

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Get the provider type identifier."""
        ...

    @abstractmethod
    def create_client(self, options: Any) -> AIClient:
        """Create a new AI client with the given options.

        Args:
            options: Provider-specific options object

        Returns:
            Configured AIClient ready for connection
        """
        ...

    @abstractmethod
    def build_options(
        self,
        base_options: AIClientOptions,
        anthropic_calls_capture: Optional[List[str]] = None,
        skip_tool_capture: Optional[List[bool]] = None,
        excuse_reasons_capture: Optional[List[str]] = None,
    ) -> Any:
        """Build provider-specific options from base configuration.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: List to capture anthropic tool calls
            skip_tool_capture: List to capture skip tool usage
            excuse_reasons_capture: List to capture excuse tool reasons

        Returns:
            Provider-specific options object
        """
        ...

    @abstractmethod
    def get_parser(self) -> AIStreamParser:
        """Get the stream parser for this provider.

        Returns:
            Parser instance for parsing provider messages
        """
        ...

    @abstractmethod
    async def check_availability(self) -> bool:
        """Check if the provider is available and authenticated.

        Returns:
            True if provider is ready to use, False otherwise
        """
        ...

    def get_session_key_field(self) -> str:
        """Get the database field name for this provider's session ID.

        Returns:
            Field name (e.g., 'claude_session_id', 'codex_thread_id')
        """
        if self.provider_type == ProviderType.CLAUDE:
            return "claude_session_id"
        elif self.provider_type == ProviderType.CODEX:
            return "codex_thread_id"
        return "session_id"  # Fallback
