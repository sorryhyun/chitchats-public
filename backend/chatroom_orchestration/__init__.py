"""
Chat orchestration module for multi-agent conversations.

This module provides functionality for orchestrating multi-agent conversations,
building conversation context, and saving messages to the database.
"""

from .context import build_conversation_context, detect_conversation_type, get_user_name_from_messages
from .handlers import save_agent_message
from .orchestrator import MAX_FOLLOW_UP_ROUNDS, MAX_TOTAL_MESSAGES, ChatOrchestrator

__all__ = [
    "ChatOrchestrator",
    "MAX_FOLLOW_UP_ROUNDS",
    "MAX_TOTAL_MESSAGES",
    "build_conversation_context",
    "detect_conversation_type",
    "get_user_name_from_messages",
    "save_agent_message",
]
