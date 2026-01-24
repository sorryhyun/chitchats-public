"""
Message handlers for saving chat messages to database.

ChitChats uses HTTP polling architecture (clients poll every 2 seconds),
so no real-time broadcasting is needed - messages are simply saved to the
database and retrieved via polling.
"""

import logging

import crud
import schemas
from domain.contexts import AgentMessageData, MessageContext

logger = logging.getLogger("MessageHandlers")


async def save_agent_message(context: MessageContext, message_data: AgentMessageData):
    """Save agent message to database.

    Args:
        context: MessageContext containing db, room, and agent
        message_data: AgentMessageData containing message content and thinking

    Returns:
        The saved message database ID
    """
    agent_message = schemas.MessageCreate(
        content=message_data.content,
        role="assistant",
        agent_id=context.agent.id,
        thinking=message_data.thinking if message_data.thinking else None,
        anthropic_calls=message_data.anthropic_calls if message_data.anthropic_calls else None,
    )
    # Update room activity for agent messages so unread notifications appear
    saved_msg = await crud.create_message(context.db, context.room_id, agent_message, update_room_activity=True)
    return saved_msg.id
