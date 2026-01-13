"""
Consolidated context data structures.

Contains all context dataclasses for operations throughout the application.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Union

from .agent_config import AgentConfigData
from .task_identifier import TaskIdentifier

if TYPE_CHECKING:
    from infrastructure.database import Agent
    from sdk import AgentManager
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class MessageContext:
    """
    Context for message operations.

    This dataclass groups parameters for message-related operations,
    reducing parameter count in handler functions.

    Attributes:
        db: Database session
        room_id: Room ID
        agent: Agent object
    """

    db: "AsyncSession"
    room_id: int
    agent: "Agent"


@dataclass
class AgentMessageData:
    """
    Data for agent message to broadcast.

    Attributes:
        content: The message content
        thinking: Optional thinking text from the agent
        anthropic_calls: Optional list of anthropic tool call situations
    """

    content: str
    thinking: Optional[str] = None
    anthropic_calls: Optional[list[str]] = None


@dataclass
class OrchestrationContext:
    """
    Shared context for orchestration operations.

    This dataclass groups the common parameters passed through
    orchestration methods, reducing repetition.

    Attributes:
        db: Database session
        room_id: Room ID
        agent_manager: AgentManager for generating responses
    """

    db: "AsyncSession"
    room_id: int
    agent_manager: "AgentManager"


@dataclass
class ImageAttachment:
    """
    Image attachment data for multimodal messages.

    Attributes:
        data: Base64-encoded image data (without data URL prefix)
        media_type: MIME type (e.g., 'image/png', 'image/jpeg')
    """

    data: str
    media_type: str


@dataclass
class AgentResponseContext:
    """
    Context required for generating agent responses.

    This dataclass groups all parameters needed by AgentManager.generate_sdk_response(),
    reducing the parameter count from 11 to 1.

    Attributes:
        system_prompt: The system prompt that defines the agent's behavior
        user_message: The user's message - either a string or list of content blocks
                      (text/image dicts for native multimodal support)
        agent_name: The name of the agent (used for dynamic agent settings)
        config: Agent configuration data (grouped)
        room_id: Room ID where this response is being generated
        agent_id: Agent ID generating the response
        group_name: Optional group name for applying group-specific tool config overrides
        session_id: Optional session ID to resume a previous conversation
        conversation_history: Optional recent conversation context for multi-agent rooms
        task_id: Optional unique identifier for tracking this task (for interruption)
        conversation_started: Optional timestamp when the conversation started
        has_situation_builder: Whether the room has a situation builder participant
        provider: AI provider to use ('claude' or 'codex'), defaults to 'claude'
    """

    system_prompt: str
    user_message: Union[str, List[dict]]
    agent_name: str
    config: AgentConfigData
    room_id: int
    agent_id: int
    group_name: Optional[str] = None
    session_id: Optional[str] = None
    conversation_history: Optional[str] = None
    task_id: Optional[TaskIdentifier] = None
    conversation_started: Optional[str] = None
    has_situation_builder: bool = False
    provider: str = "claude"  # AI provider: 'claude' or 'codex'
