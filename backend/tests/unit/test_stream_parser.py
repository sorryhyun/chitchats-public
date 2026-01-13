"""
Unit tests for StreamParser - SDK message parsing logic.
"""

from unittest.mock import Mock

from providers.base import ParsedStreamMessage
from providers.claude.parser import ClaudeStreamParser as StreamParser


class TestParsedStreamMessage:
    """Test ParsedStreamMessage dataclass."""

    def test_has_tool_usage_with_skip(self):
        """Test has_tool_usage property when skip is used."""
        msg = ParsedStreamMessage(response_text="Hello", thinking_text="", skip_used=True, memory_entries=[])
        assert msg.has_tool_usage is True

    def test_has_tool_usage_with_memory(self):
        """Test has_tool_usage property when memories are recorded."""
        msg = ParsedStreamMessage(
            response_text="Hello", thinking_text="", skip_used=False, memory_entries=["Test memory"]
        )
        assert msg.has_tool_usage is True

    def test_has_tool_usage_with_both(self):
        """Test has_tool_usage property with both skip and memory."""
        msg = ParsedStreamMessage(
            response_text="Hello", thinking_text="", skip_used=True, memory_entries=["Memory 1", "Memory 2"]
        )
        assert msg.has_tool_usage is True

    def test_has_tool_usage_with_none(self):
        """Test has_tool_usage property when no tools used."""
        msg = ParsedStreamMessage(response_text="Hello", thinking_text="", skip_used=False, memory_entries=[])
        assert msg.has_tool_usage is False

    def test_default_values(self):
        """Test default values for optional fields."""
        msg = ParsedStreamMessage(response_text="Hello", thinking_text="World")
        assert msg.session_id is None
        assert msg.skip_used is False
        assert msg.memory_entries == []


class TestStreamParser:
    """Test StreamParser message parsing logic."""

    def test_parse_text_content_with_text_attribute(self):
        """Test parsing message with direct text attribute."""
        message = Mock()
        message.text = "Hello, world!"

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Hello, world!"
        assert result.thinking_text == ""
        assert result.session_id is None
        assert not result.has_tool_usage

    def test_parse_text_content_string(self):
        """Test parsing message with string content."""
        message = Mock()
        del message.text  # Remove text attribute
        message.content = "Hello from string content"

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Hello from string content"
        assert result.thinking_text == ""

    def test_parse_text_block_in_content_list(self):
        """Test parsing AssistantMessage with TextBlock in content list."""
        # Mock TextBlock
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "This is text content"

        # Mock AssistantMessage
        message = Mock()
        del message.text  # No direct text attribute
        message.content = [text_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "This is text content"
        assert result.thinking_text == ""

    def test_parse_thinking_block_with_thinking_attribute(self):
        """Test parsing ThinkingBlock with thinking attribute."""
        # Mock ThinkingBlock
        thinking_block = Mock()
        thinking_block.__class__.__name__ = "ThinkingBlock"
        thinking_block.thinking = "Agent is thinking..."
        thinking_block.type = "thinking"

        # Mock message
        message = Mock()
        del message.text
        message.content = [thinking_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == ""
        assert result.thinking_text == "Agent is thinking..."

    def test_parse_thinking_block_with_text_fallback(self):
        """Test parsing ThinkingBlock with text fallback."""
        # Mock ThinkingBlock with text instead of thinking
        thinking_block = Mock()
        thinking_block.__class__.__name__ = "ThinkingBlock"
        del thinking_block.thinking  # No thinking attribute
        thinking_block.text = "Thinking via text attribute"
        thinking_block.type = "thinking"

        message = Mock()
        del message.text
        message.content = [thinking_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.thinking_text == "Thinking via text attribute"

    def test_parse_thinking_block_dict_format(self):
        """Test parsing thinking block in dict format."""
        # Mock thinking block as dict
        thinking_block = {"type": "thinking", "thinking": "Dictionary thinking content"}

        message = Mock()
        del message.text
        message.content = [thinking_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.thinking_text == "Dictionary thinking content"

    def test_parse_skip_tool_call(self):
        """Test that skip tool is NOT detected in stream parser.

        Skip detection has been moved to PostToolUse hooks for MCP tools.
        Stream parser no longer detects skip tool calls.
        """
        # Mock ToolUseBlock for skip
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent_name__skip"
        # Ensure text attribute doesn't exist to avoid falling into text handling
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        # Skip is now detected via hooks, not stream parser
        assert result.skip_used is False
        assert result.has_tool_usage is False

    def test_parse_skip_tool_call_dict_format(self):
        """Test that skip tool in dict format is NOT detected in stream parser."""
        tool_block = {"type": "tool_use", "name": "some_agent__skip"}

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        # Skip is now detected via hooks, not stream parser
        assert result.skip_used is False

    def test_parse_memorize_tool_call(self):
        """Test parsing memorize tool usage."""
        # Mock ToolUseBlock for memorize
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent_name__memorize"
        tool_block.input = {"memory_entry": "Important memory to save"}
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.memory_entries == ["Important memory to save"]
        assert result.has_tool_usage is True

    def test_parse_memorize_tool_call_dict_format(self):
        """Test parsing memorize tool in dict format."""
        tool_block = {"type": "tool_use", "name": "agent__memorize", "input": {"memory_entry": "Memory in dict format"}}

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.memory_entries == ["Memory in dict format"]

    def test_parse_multiple_memory_entries(self):
        """Test parsing multiple memorize tool calls."""
        tool_block1 = Mock()
        tool_block1.type = "tool_use"
        tool_block1.name = "agent__memorize"
        tool_block1.input = {"memory_entry": "Memory 1"}
        if hasattr(tool_block1, "text"):
            del tool_block1.text

        tool_block2 = Mock()
        tool_block2.type = "tool_use"
        tool_block2.name = "agent__memorize"
        tool_block2.input = {"memory_entry": "Memory 2"}
        if hasattr(tool_block2, "text"):
            del tool_block2.text

        message = Mock()
        del message.text
        message.content = [tool_block1, tool_block2]

        result = StreamParser.parse_message(message, "", "")

        assert result.memory_entries == ["Memory 1", "Memory 2"]

    def test_parse_system_message_with_session_id(self):
        """Test extracting session_id from SystemMessage."""
        message = Mock()
        message.__class__.__name__ = "SystemMessage"
        message.data = {"session_id": "sess_abc123", "other": "data"}
        del message.text
        del message.content

        result = StreamParser.parse_message(message, "", "")

        assert result.session_id == "sess_abc123"

    def test_parse_system_message_without_session_id(self):
        """Test SystemMessage without session_id."""
        message = Mock()
        message.__class__.__name__ = "SystemMessage"
        message.data = {"other": "data"}
        del message.text
        del message.content

        result = StreamParser.parse_message(message, "", "")

        assert result.session_id is None

    def test_parse_accumulated_text(self):
        """Test that parser accumulates text from previous messages."""
        text_block = Mock()
        text_block.type = "text"
        text_block.text = " more text"

        message = Mock()
        del message.text
        message.content = [text_block]

        result = StreamParser.parse_message(message, "Previous", "Existing thinking")

        assert result.response_text == "Previous more text"
        assert result.thinking_text == "Existing thinking"

    def test_parse_mixed_content_blocks(self):
        """Test parsing message with mixed content blocks."""
        # Text block
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "Hello"

        # Thinking block
        thinking_block = Mock()
        thinking_block.__class__.__name__ = "ThinkingBlock"
        thinking_block.thinking = "Processing..."
        thinking_block.type = "thinking"
        if hasattr(thinking_block, "text"):
            del thinking_block.text

        # Tool use block (skip - no longer detected in stream parser)
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent__skip"
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [text_block, thinking_block, tool_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Hello"
        assert result.thinking_text == "Processing..."
        # Skip is now detected via hooks, not stream parser
        assert result.skip_used is False

    def test_parse_multiple_text_blocks(self):
        """Test parsing multiple text blocks accumulates content."""
        text_block1 = Mock()
        text_block1.type = "text"
        text_block1.text = "Part 1 "

        text_block2 = Mock()
        text_block2.type = "text"
        text_block2.text = "Part 2"

        message = Mock()
        del message.text
        message.content = [text_block1, text_block2]

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Part 1 Part 2"

    def test_parse_empty_message(self):
        """Test parsing message with no content."""
        message = Mock()
        del message.text
        del message.content

        result = StreamParser.parse_message(message, "Existing", "Thinking")

        assert result.response_text == "Existing"
        assert result.thinking_text == "Thinking"
        assert result.session_id is None
        assert not result.has_tool_usage

    def test_parse_text_block_dict_format(self):
        """Test parsing text block in dict format."""
        text_block = {"type": "text", "text": "Dictionary text content"}

        message = Mock()
        del message.text
        message.content = [text_block]

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Dictionary text content"

    def test_parse_memorize_without_memory_entry(self):
        """Test memorize tool without memory_entry field."""
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent__memorize"
        tool_block.input = {"other_field": "value"}
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        # Should not add empty memory
        assert result.memory_entries == []

    def test_parse_memorize_with_empty_memory_entry(self):
        """Test memorize tool with empty memory_entry."""
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent__memorize"
        tool_block.input = {"memory_entry": ""}
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        # Should not add empty memory
        assert result.memory_entries == []

    def test_parse_unknown_tool_call(self):
        """Test parsing unknown tool call doesn't affect flags."""
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.name = "agent__unknown_tool"
        tool_block.input = {}
        if hasattr(tool_block, "text"):
            del tool_block.text

        message = Mock()
        del message.text
        message.content = [tool_block]

        result = StreamParser.parse_message(message, "", "")

        assert not result.skip_used
        assert result.memory_entries == []
        assert not result.has_tool_usage
