"""
Unit tests for orchestration context builder.

Tests conversation context building from room messages.
"""

import os
from unittest.mock import Mock, patch

from chatroom_orchestration.context import build_conversation_context


def extract_text_from_blocks(content_blocks: list) -> str:
    """Helper to extract text content from content blocks for testing."""
    if not content_blocks:
        return ""
    return "\n".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")


class TestBuildConversationContext:
    """Tests for build_conversation_context function."""

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_no_messages(self, mock_get_config):
        """Test building context with no messages."""
        mock_get_config.return_value = {
            "conversation_context": {
                "header": "Conversation:",
                "footer": "",
            }
        }

        content_blocks = build_conversation_context([])

        assert content_blocks == []

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    @patch("chatroom_orchestration.context._settings")
    def test_build_context_with_user_messages(self, mock_settings, mock_get_config):
        """Test building context with user messages."""
        mock_get_config.return_value = {
            "conversation_context": {
                "header": "Conversation:",
                "footer": "",
            }
        }

        # Mock the settings object to return our test user name
        mock_settings.user_name = "TestUser"

        # Create mock messages with image_data=None and images=None to avoid Mock truthiness
        msg1 = Mock(
            role="user",
            content="Hello!",
            participant_type="user",
            participant_name=None,
            agent_id=None,
            image_data=None,
            images=None,
        )

        msg2 = Mock(
            role="user",
            content="How are you?",
            participant_type="user",
            participant_name=None,
            agent_id=None,
            image_data=None,
            images=None,
        )

        content_blocks = build_conversation_context([msg1, msg2])
        context = extract_text_from_blocks(content_blocks)

        assert "Conversation:" in context
        assert "TestUser:\nHello!" in context
        assert "TestUser:\nHow are you?" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_agent_messages(self, mock_get_config):
        """Test building context with agent messages."""
        mock_get_config.return_value = {"conversation_context": {"header": "Conversation:", "footer": ""}}

        # Create mock agent with name attribute properly set
        mock_agent = Mock()
        mock_agent.name = "Alice"

        msg = Mock(role="assistant", content="Hi there!", agent_id=1, agent=mock_agent, image_data=None, images=None)

        content_blocks = build_conversation_context([msg])
        context = extract_text_from_blocks(content_blocks)

        assert "Alice:\nHi there!" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_skips_skip_messages(self, mock_get_config):
        """Test that skip messages are excluded from context."""
        mock_get_config.return_value = {"conversation_context": {"header": "Conversation:", "footer": ""}}

        # Import SKIP_MESSAGE_TEXT
        from core.settings import SKIP_MESSAGE_TEXT

        msg1 = Mock(
            role="assistant",
            content=SKIP_MESSAGE_TEXT,
            agent_id=1,
            agent=Mock(name="Alice"),
            image_data=None,
            images=None,
        )

        msg2 = Mock(
            role="assistant", content="Real message", agent_id=2, agent=Mock(name="Bob"), image_data=None, images=None
        )

        content_blocks = build_conversation_context([msg1, msg2])
        context = extract_text_from_blocks(content_blocks)

        # Should not include skip message
        assert SKIP_MESSAGE_TEXT not in context
        assert "Real message" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_agent_id_filter(self, mock_get_config):
        """Test building context with agent_id filter (only new messages)."""
        mock_get_config.return_value = {"conversation_context": {"header": "Conversation:", "footer": ""}}

        # Create messages before and after agent's last response
        messages = [
            Mock(
                role="user", content="Message 1", agent_id=None, participant_type="user", image_data=None, images=None
            ),
            Mock(
                role="assistant",
                content="Agent response",
                agent_id=1,
                agent=Mock(name="Alice"),
                image_data=None,
                images=None,
            ),
            Mock(
                role="user", content="Message 2", agent_id=None, participant_type="user", image_data=None, images=None
            ),
            Mock(
                role="user", content="Message 3", agent_id=None, participant_type="user", image_data=None, images=None
            ),
        ]

        with patch.dict(os.environ, {"USER_NAME": "User"}):
            content_blocks = build_conversation_context(messages, agent_id=1)
            context = extract_text_from_blocks(content_blocks)

        # Should only include messages after agent's last response
        assert "Message 1" not in context
        assert "Agent response" not in context
        assert "Message 2" in context
        assert "Message 3" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_limit(self, mock_get_config):
        """Test building context respects message limit."""
        mock_get_config.return_value = {"conversation_context": {"header": "", "footer": ""}}

        # Create many messages
        messages = [
            Mock(
                role="user",
                content=f"Message {i}",
                agent_id=None,
                participant_type="user",
                image_data=None,
                images=None,
            )
            for i in range(100)
        ]

        content_blocks = build_conversation_context(messages, limit=5)
        context = extract_text_from_blocks(content_blocks)

        # Should only include last 5 messages (+ header/footer)
        assert "Message 95" in context
        assert "Message 99" in context
        assert "Message 0" not in context
        assert "Message 90" not in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_character_participant(self, mock_get_config):
        """Test building context with character participant type."""
        mock_get_config.return_value = {"conversation_context": {"header": "", "footer": ""}}

        msg = Mock(
            role="user",
            content="Hello from character!",
            participant_type="character",
            participant_name="Charlie",
            agent_id=None,
            image_data=None,
            images=None,
        )

        content_blocks = build_conversation_context([msg])
        context = extract_text_from_blocks(content_blocks)

        # Should use participant_name as speaker
        assert "Charlie:\nHello from character!" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_with_situation_builder(self, mock_get_config):
        """Test building context with situation_builder participant."""
        mock_get_config.return_value = {"conversation_context": {"header": "", "footer": ""}}

        msg = Mock(
            role="user",
            content="Scenario description",
            participant_type="situation_builder",
            participant_name=None,
            agent_id=None,
            image_data=None,
            images=None,
        )

        content_blocks = build_conversation_context([msg])
        context = extract_text_from_blocks(content_blocks)

        # Should use "Situation Builder" as speaker
        assert "Situation Builder:\nScenario description" in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    @patch("chatroom_orchestration.context.format_with_particles")
    def test_build_context_with_response_instruction(self, mock_format_particles, mock_get_config):
        """Test response instruction is added when agent_name is provided."""
        mock_get_config.return_value = {
            "conversation_context": {
                "header": "",
                "footer": "",
                "response_instruction": "Respond as {agent_name}.",
            }
        }
        mock_format_particles.return_value = "Respond as Alice."

        msg = Mock(
            role="user",
            content="Hello",
            participant_type="user",
            participant_name=None,
            agent_id=None,
            image_data=None,
            images=None,
        )

        content_blocks = build_conversation_context([msg], agent_name="Alice")
        context = extract_text_from_blocks(content_blocks)

        # Should use response instruction template
        mock_format_particles.assert_called_once()
        assert "Respond as Alice." in context

    @patch("chatroom_orchestration.context.get_conversation_context_config")
    def test_build_context_deduplicates_messages(self, mock_get_config):
        """Test that duplicate messages are filtered out."""
        mock_get_config.return_value = {"conversation_context": {"header": "", "footer": ""}}

        # Create duplicate messages
        messages = [
            Mock(
                role="user",
                content="Same message",
                agent_id=None,
                participant_type="user",
                participant_name=None,
                image_data=None,
                images=None,
            ),
            Mock(
                role="user",
                content="Same message",
                agent_id=None,
                participant_type="user",
                participant_name=None,
                image_data=None,
                images=None,
            ),
            Mock(
                role="user",
                content="Different message",
                agent_id=None,
                participant_type="user",
                participant_name=None,
                image_data=None,
                images=None,
            ),
        ]

        with patch.dict(os.environ, {"USER_NAME": "User"}):
            content_blocks = build_conversation_context(messages)
            context = extract_text_from_blocks(content_blocks)

        # Should only include "Same message" once
        assert context.count("Same message") == 1
        assert "Different message" in context
