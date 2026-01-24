"""
Unit tests for orchestration message handlers.

Tests message saving functionality for polling architecture.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from domain.contexts import AgentMessageData, MessageContext
from chatroom_orchestration.handlers import save_agent_message


class TestSaveAgentMessage:
    """Tests for save_agent_message function."""

    @pytest.mark.asyncio
    async def test_save_message_with_thinking(self):
        """Test saving agent message with thinking text."""
        mock_db = AsyncMock()
        mock_agent = Mock(id=1, name="Alice", profile_pic="pic.jpg")

        saved_message = Mock(id=123, content="Hello world", role="assistant", timestamp=datetime.utcnow())

        with patch("chatroom_orchestration.handlers.crud.create_message", return_value=saved_message) as mock_create:
            context = MessageContext(
                db=mock_db,
                room_id=1,
                agent=mock_agent,
            )

            message_data = AgentMessageData(content="Hello world", thinking="Thinking process")

            msg_id = await save_agent_message(context, message_data)

            # Should save message to database
            mock_create.assert_awaited_once()
            create_call_args = mock_create.call_args[0]
            assert create_call_args[1] == 1  # room_id

            # Verify message content
            message_arg = mock_create.call_args[0][2]
            assert message_arg.content == "Hello world"
            assert message_arg.thinking == "Thinking process"

            # Should return message ID
            assert msg_id == 123

    @pytest.mark.asyncio
    async def test_save_message_without_thinking(self):
        """Test saving agent message without thinking text."""
        mock_db = AsyncMock()
        mock_agent = Mock(id=1, name="Alice")

        saved_message = Mock(id=456, content="Hello", timestamp=datetime.utcnow())

        with patch("chatroom_orchestration.handlers.crud.create_message", return_value=saved_message) as mock_create:
            context = MessageContext(
                db=mock_db,
                room_id=1,
                agent=mock_agent,
            )

            message_data = AgentMessageData(content="Hello")

            msg_id = await save_agent_message(context, message_data)

            # Thinking should be None in saved message
            message_arg = mock_create.call_args[0][2]
            assert message_arg.thinking is None

            assert msg_id == 456

    @pytest.mark.asyncio
    async def test_save_message_updates_room_activity(self):
        """Test that saving message updates room activity for unread notifications."""
        mock_db = AsyncMock()
        mock_agent = Mock(id=1, name="Alice")

        saved_message = Mock(id=789, timestamp=datetime.utcnow())

        with patch("chatroom_orchestration.handlers.crud.create_message", return_value=saved_message) as mock_create:
            context = MessageContext(
                db=mock_db,
                room_id=1,
                agent=mock_agent,
            )

            message_data = AgentMessageData(content="Test message")

            await save_agent_message(context, message_data)

            # Verify update_room_activity=True was passed
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs.get("update_room_activity") is True
