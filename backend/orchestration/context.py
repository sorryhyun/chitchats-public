"""
Conversation context builder for multi-agent chat rooms.

This module provides functionality to build conversation context from
recent room messages for multi-agent awareness.
"""

from typing import List, Optional

from core import get_settings
from core.settings import SKIP_MESSAGE_TEXT
from domain.enums import ParticipantType
from i18n.korean import format_with_particles
from config import get_conversation_context_config

from orchestration.whiteboard import process_messages_for_whiteboard

# Get settings singleton
_settings = get_settings()


def build_conversation_context(
    messages: List,
    limit: int = 25,
    agent_id: Optional[int] = None,
    agent_name: Optional[str] = None,
    agent_count: Optional[int] = None,
    user_name: Optional[str] = None,
    include_response_instruction: bool = True,
    provider: Optional[str] = None,
) -> List[dict]:
    """
    Build conversation context from recent room messages for multi-agent awareness.

    Returns a list of content blocks (text and image) for native multimodal support.
    Images are positioned inline within the conversation structure.

    Args:
        messages: List of recent messages from the room
        limit: Maximum number of recent messages to include
        agent_id: If provided, only include messages after this agent's last response
        agent_name: Optional agent name to include in the thinking block instruction
        agent_count: Number of agents in the room (for detecting 1-on-1 conversations)
        user_name: Name of the user/character participant (for 1-on-1 conversations)
        include_response_instruction: If True, append response instruction; if False, only include conversation history
        provider: AI provider ('claude' or 'codex') for provider-specific instructions

    Returns:
        List of content blocks: [{"type": "text", "text": "..."}, {"type": "image", "source": {...}}, ...]
    """
    if not messages:
        return []

    # If agent_id is provided, find messages after the agent's last response
    if agent_id is not None:
        # Find the index of the agent's last message
        last_agent_msg_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].agent_id == agent_id:
                last_agent_msg_idx = i
                break

        # If agent has responded before, only include messages after that
        if last_agent_msg_idx >= 0:
            recent_messages = messages[last_agent_msg_idx + 1 :]
        else:
            # Agent hasn't responded yet, use recent messages
            recent_messages = messages[-limit:] if len(messages) > limit else messages
    else:
        # No agent_id provided, use recent messages
        recent_messages = messages[-limit:] if len(messages) > limit else messages

    # If no new messages, return empty
    if not recent_messages:
        return []

    # Load conversation context configuration
    context_config = get_conversation_context_config()
    config = context_config.get("conversation_context", {})

    # Build content blocks list for multimodal support
    content_blocks: List[dict] = []

    # Start with header
    header = config.get("header", "Here's the conversation so far:")
    current_text = header + "\n"

    # Process whiteboard messages to get rendered content (accumulated state)
    # This converts diff format to full rendered whiteboard for other agents
    whiteboard_rendered = process_messages_for_whiteboard(messages)

    # Track seen messages to avoid duplicates (speaker, content) pairs
    seen_messages = set()

    for msg in recent_messages:
        # Skip messages that are marked as "skip" (invisible to others)
        # Also handle legacy Korean text for backward compatibility
        if msg.content == SKIP_MESSAGE_TEXT or msg.content == "(무시함)":
            continue

        # Skip system messages (e.g., "X joined the chat") - these are UI-only notifications
        if msg.participant_type == ParticipantType.SYSTEM:
            continue

        # Format each message with speaker identification
        if msg.role == "user":
            # Use participant_name if provided, otherwise determine by type
            if msg.participant_name:
                speaker = msg.participant_name
            elif msg.participant_type == ParticipantType.SITUATION_BUILDER:
                speaker = "Situation Builder"
            else:
                # Default to USER_NAME or "User"
                speaker = _settings.user_name
        elif msg.agent_id:
            # Get agent name from the message relationship
            speaker = msg.agent.name if hasattr(msg, "agent") and msg.agent else f"Agent {msg.agent_id}"
        else:
            speaker = "Unknown"

        # Create a unique key for this message (speaker + content)
        message_key = (speaker, msg.content)

        # Skip if we've already seen this exact message from this speaker
        if message_key in seen_messages:
            continue

        seen_messages.add(message_key)

        # Get message content (use rendered whiteboard content if available)
        content = whiteboard_rendered.get(msg.id, msg.content)

        # Check if message has an image for native multimodal support
        has_image = (
            hasattr(msg, "image_data") and msg.image_data and hasattr(msg, "image_media_type") and msg.image_media_type
        )

        if has_image:
            # Add accumulated text as a block, then image inline
            current_text += f"{speaker}: "
            if current_text.strip():
                content_blocks.append({"type": "text", "text": current_text})

            # Add native image block
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": msg.image_media_type,
                        "data": msg.image_data,
                    },
                }
            )

            # Continue with content after image
            if content:
                current_text = f"\n{content}\n"
            else:
                current_text = "\n"
        else:
            # No image - just add text with colon format
            current_text += f"{speaker}: {content}\n"

    # Add footer (closing tag) after conversation messages
    footer = config.get("footer", "")
    if footer:
        current_text += footer + "\n"

    # Add recall tool reminder when including instructions
    if include_response_instruction:
        recall_reminder = config.get("recall_reminder", "")
        if recall_reminder:
            current_text += f"\n{recall_reminder}\n"

    # Add response instruction (if requested)
    if include_response_instruction and agent_name:
        # Try provider-specific instruction first, fall back to generic
        instruction = ""
        if provider:
            instruction = config.get(f"response_instruction_{provider}", "")
        if not instruction:
            instruction = config.get("response_instruction", "")
        if instruction:
            current_text += format_with_particles(instruction, agent_name=agent_name, user_name=user_name or "")

    # Add any remaining text as a final block
    if current_text.strip():
        content_blocks.append({"type": "text", "text": current_text.strip()})

    return content_blocks
