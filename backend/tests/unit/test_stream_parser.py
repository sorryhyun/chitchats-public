"""
Unit tests for ClaudeStreamParser - Claude SDK message parsing logic.

Tests the stream parser that converts Claude SDK messages into
unified ParsedStreamMessage format.
"""

from unittest.mock import Mock

from claude_agent_sdk import AssistantMessage, SystemMessage, TextBlock, ThinkingBlock, ToolUseBlock

from providers.base import ParsedStreamMessage
from providers.claude.parser import ClaudeStreamParser as StreamParser


def _make_assistant_message(content: list) -> Mock:
    """Create a mock AssistantMessage with the given content blocks."""
    msg = Mock(spec=AssistantMessage)
    msg.content = content
    return msg


def _make_system_message(subtype: str = "init", data: dict | None = None) -> Mock:
    """Create a mock SystemMessage."""
    msg = Mock(spec=SystemMessage)
    msg.subtype = subtype
    msg.data = data or {}
    return msg


def _make_text_block(text: str) -> Mock:
    """Create a mock TextBlock."""
    block = Mock(spec=TextBlock)
    block.text = text
    return block


def _make_thinking_block(thinking: str) -> Mock:
    """Create a mock ThinkingBlock."""
    block = Mock(spec=ThinkingBlock)
    block.thinking = thinking
    return block


def _make_tool_use_block(name: str, input_data: dict | None = None) -> Mock:
    """Create a mock ToolUseBlock."""
    block = Mock(spec=ToolUseBlock)
    block.name = name
    block.input = input_data or {}
    return block


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

    def test_parse_text_block_in_content_list(self):
        """Test parsing AssistantMessage with TextBlock in content list."""
        message = _make_assistant_message([_make_text_block("This is text content")])

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "This is text content"
        assert result.thinking_text == ""

    def test_parse_thinking_block(self):
        """Test parsing ThinkingBlock with thinking attribute."""
        message = _make_assistant_message([_make_thinking_block("Agent is thinking...")])

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == ""
        assert result.thinking_text == "Agent is thinking..."

    def test_parse_skip_tool_call(self):
        """Test that skip tool is NOT detected in stream parser.

        Skip detection has been moved to PostToolUse hooks for MCP tools.
        Stream parser no longer detects skip tool calls.
        """
        message = _make_assistant_message([_make_tool_use_block("agent_name__skip")])

        result = StreamParser.parse_message(message, "", "")

        # Skip is now detected via hooks, not stream parser
        assert result.skip_used is False
        assert result.has_tool_usage is False

    def test_parse_memorize_tool_call(self):
        """Test parsing memorize tool usage."""
        message = _make_assistant_message([
            _make_tool_use_block("agent_name__memorize", {"memory_entry": "Important memory to save"})
        ])

        result = StreamParser.parse_message(message, "", "")

        assert result.memory_entries == ["Important memory to save"]
        assert result.has_tool_usage is True

    def test_parse_multiple_memory_entries(self):
        """Test parsing multiple memorize tool calls."""
        message = _make_assistant_message([
            _make_tool_use_block("agent__memorize", {"memory_entry": "Memory 1"}),
            _make_tool_use_block("agent__memorize", {"memory_entry": "Memory 2"}),
        ])

        result = StreamParser.parse_message(message, "", "")

        assert result.memory_entries == ["Memory 1", "Memory 2"]

    def test_parse_system_message_with_session_id(self):
        """Test extracting session_id from SystemMessage."""
        message = _make_system_message(
            subtype="init",
            data={"session_id": "sess_abc123", "other": "data"},
        )

        result = StreamParser.parse_message(message, "", "")

        assert result.session_id == "sess_abc123"

    def test_parse_system_message_without_session_id(self):
        """Test SystemMessage without session_id."""
        message = _make_system_message(subtype="init", data={"other": "data"})

        result = StreamParser.parse_message(message, "", "")

        assert result.session_id is None

    def test_parse_system_message_rate_limit(self):
        """Test SystemMessage with rate_limit subtype doesn't crash."""
        message = _make_system_message(
            subtype="rate_limit",
            data={"message": "Too many requests"},
        )

        result = StreamParser.parse_message(message, "", "")

        assert result.session_id is None

    def test_parse_accumulated_text(self):
        """Test that parser accumulates text from previous messages."""
        message = _make_assistant_message([_make_text_block(" more text")])

        result = StreamParser.parse_message(message, "Previous", "Existing thinking")

        # When current_response is non-empty, text blocks are skipped (dedup with StreamEvent)
        # so response stays "Previous"
        assert result.response_text == "Previous"
        assert result.thinking_text == "Existing thinking"

    def test_parse_accumulated_text_fresh(self):
        """Test that text blocks are used when no prior streamed content."""
        message = _make_assistant_message([_make_text_block("fresh text")])

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "fresh text"

    def test_parse_mixed_content_blocks(self):
        """Test parsing message with mixed content blocks."""
        message = _make_assistant_message([
            _make_text_block("Hello"),
            _make_thinking_block("Processing..."),
            _make_tool_use_block("agent__skip"),
        ])

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Hello"
        assert result.thinking_text == "Processing..."
        # Skip is now detected via hooks, not stream parser
        assert result.skip_used is False

    def test_parse_multiple_text_blocks(self):
        """Test parsing multiple text blocks accumulates content."""
        message = _make_assistant_message([
            _make_text_block("Part 1 "),
            _make_text_block("Part 2"),
        ])

        result = StreamParser.parse_message(message, "", "")

        assert result.response_text == "Part 1 Part 2"

    def test_parse_empty_message(self):
        """Test parsing unknown message type with no content."""
        message = Mock()  # Not any known type

        result = StreamParser.parse_message(message, "Existing", "Thinking")

        assert result.response_text == "Existing"
        assert result.thinking_text == "Thinking"
        assert result.session_id is None
        assert not result.has_tool_usage

    def test_parse_memorize_without_memory_entry(self):
        """Test memorize tool without memory_entry field."""
        message = _make_assistant_message([
            _make_tool_use_block("agent__memorize", {"other_field": "value"})
        ])

        result = StreamParser.parse_message(message, "", "")

        # Should not add empty memory
        assert result.memory_entries == []

    def test_parse_memorize_with_empty_memory_entry(self):
        """Test memorize tool with empty memory_entry."""
        message = _make_assistant_message([
            _make_tool_use_block("agent__memorize", {"memory_entry": ""})
        ])

        result = StreamParser.parse_message(message, "", "")

        # Should not add empty memory
        assert result.memory_entries == []

    def test_parse_unknown_tool_call(self):
        """Test parsing unknown tool call doesn't affect flags."""
        message = _make_assistant_message([
            _make_tool_use_block("agent__unknown_tool", {})
        ])

        result = StreamParser.parse_message(message, "", "")

        assert not result.skip_used
        assert result.memory_entries == []
        assert not result.has_tool_usage

    def test_thinking_skipped_when_already_streamed(self):
        """Test that thinking blocks are skipped when already streamed via StreamEvent."""
        message = _make_assistant_message([_make_thinking_block("duplicate thinking")])

        result = StreamParser.parse_message(message, "", "Already streamed thinking")

        # Thinking should not be added again
        assert result.thinking_text == "Already streamed thinking"

    def test_text_skipped_when_already_streamed(self):
        """Test that text blocks are skipped when already streamed via StreamEvent."""
        message = _make_assistant_message([_make_text_block("duplicate text")])

        result = StreamParser.parse_message(message, "Already streamed", "")

        # Text should not be added again
        assert result.response_text == "Already streamed"
