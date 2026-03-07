"""
Tests for input_json_delta streaming support.

Tests the ClaudeStreamParser handling of content_block_start, input_json_delta,
and content_block_stop events, and the ResponseAccumulator's tool input
accumulation and excuse reason extraction.
"""

from unittest.mock import Mock

from providers.base import ParsedStreamMessage
from providers.claude.parser import ClaudeStreamParser


def _make_stream_event(event_dict: dict) -> Mock:
    """Create a mock StreamEvent wrapping a raw Anthropic API event dict."""
    from claude_agent_sdk.types import StreamEvent

    mock = Mock(spec=StreamEvent)
    mock.event = event_dict
    mock.session_id = None
    return mock


class TestClaudeParserContentBlockStart:
    """Test content_block_start event handling."""

    def test_tool_use_block_start(self):
        """Parser extracts tool name and index from content_block_start."""
        event = _make_stream_event({
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_abc123",
                "name": "mcp__action__excuse",
                "input": {},
            },
        })

        result = ClaudeStreamParser.parse_message(event, "", "")

        assert result.tool_use_started is not None
        assert result.tool_use_started["index"] == 1
        assert result.tool_use_started["name"] == "mcp__action__excuse"
        assert result.input_json_delta is None
        assert result.content_block_stopped_index is None

    def test_text_block_start_ignored(self):
        """Parser ignores content_block_start for text blocks."""
        event = _make_stream_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        })

        result = ClaudeStreamParser.parse_message(event, "", "")

        assert result.tool_use_started is None

    def test_thinking_block_start_ignored(self):
        """Parser ignores content_block_start for thinking blocks."""
        event = _make_stream_event({
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking"},
        })

        result = ClaudeStreamParser.parse_message(event, "", "")

        assert result.tool_use_started is None


class TestClaudeParserInputJsonDelta:
    """Test input_json_delta event handling."""

    def test_input_json_delta_extracted(self):
        """Parser extracts partial_json from input_json_delta."""
        event = _make_stream_event({
            "type": "content_block_delta",
            "index": 1,
            "delta": {
                "type": "input_json_delta",
                "partial_json": '{"rea',
            },
        })

        result = ClaudeStreamParser.parse_message(event, "existing", "thinking")

        assert result.input_json_delta == '{"rea'
        # Text should not change
        assert result.response_text == "existing"
        assert result.thinking_text == "thinking"

    def test_text_delta_still_works(self):
        """text_delta events still work alongside input_json_delta support."""
        event = _make_stream_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "hello"},
        })

        result = ClaudeStreamParser.parse_message(event, "", "")

        assert result.response_text == "hello"
        assert result.input_json_delta is None

    def test_thinking_delta_still_works(self):
        """thinking_delta events still work alongside input_json_delta support."""
        event = _make_stream_event({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "hmm"},
        })

        result = ClaudeStreamParser.parse_message(event, "", "")

        assert result.thinking_text == "hmm"
        assert result.input_json_delta is None


class TestClaudeParserContentBlockStop:
    """Test content_block_stop event handling."""

    def test_content_block_stop_extracted(self):
        """Parser extracts index from content_block_stop."""
        event = _make_stream_event({
            "type": "content_block_stop",
            "index": 1,
        })

        result = ClaudeStreamParser.parse_message(event, "text", "thinking")

        assert result.content_block_stopped_index == 1
        assert result.response_text == "text"
        assert result.thinking_text == "thinking"


class TestResponseAccumulatorToolStreaming:
    """Test ResponseAccumulator tool input accumulation via input_json_delta."""

    def _make_parsed(self, **kwargs) -> ParsedStreamMessage:
        """Create a ParsedStreamMessage with defaults."""
        defaults = {
            "response_text": "",
            "thinking_text": "",
        }
        defaults.update(kwargs)
        return ParsedStreamMessage(**defaults)

    def test_excuse_reason_captured_from_streaming(self):
        """Full flow: content_block_start -> input_json_deltas -> content_block_stop extracts excuse reason."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        # 1. Tool use starts
        parsed = self._make_parsed(
            tool_use_started={"index": 1, "name": "mcp__action__excuse"},
        )
        acc.update_from_parsed(parsed, "temp_1")

        assert 1 in acc._streaming_tool_blocks
        assert acc._streaming_tool_blocks[1][0] == "mcp__action__excuse"

        # 2. input_json_delta chunks arrive
        for chunk in ['{"re', 'ason":', ' "I feel', ' embarrassed"}']:
            parsed = self._make_parsed(input_json_delta=chunk)
            acc.update_from_parsed(parsed, "temp_1")

        # 3. Content block stops
        parsed = self._make_parsed(content_block_stopped_index=1)
        acc.update_from_parsed(parsed, "temp_1")

        # Excuse reason should be captured
        assert acc.excuse_reasons == ["I feel embarrassed"]
        # Tool block should be cleaned up
        assert 1 not in acc._streaming_tool_blocks

    def test_non_excuse_tool_ignored(self):
        """Tool blocks that aren't excuse don't produce excuse_reasons."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        # Start a skip tool
        parsed = self._make_parsed(
            tool_use_started={"index": 0, "name": "mcp__action__skip"},
        )
        acc.update_from_parsed(parsed, "temp_1")

        # JSON delta
        parsed = self._make_parsed(input_json_delta='{}')
        acc.update_from_parsed(parsed, "temp_1")

        # Stop
        parsed = self._make_parsed(content_block_stopped_index=0)
        acc.update_from_parsed(parsed, "temp_1")

        assert acc.excuse_reasons == []

    def test_multiple_tool_blocks(self):
        """Multiple tool blocks are tracked independently."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        # Start first tool (memorize) at index 0
        acc.update_from_parsed(
            self._make_parsed(tool_use_started={"index": 0, "name": "mcp__brain__memorize"}),
            "temp_1",
        )

        # Start second tool (excuse) at index 1
        acc.update_from_parsed(
            self._make_parsed(tool_use_started={"index": 1, "name": "mcp__action__excuse"}),
            "temp_1",
        )

        assert len(acc._streaming_tool_blocks) == 2

        # Stop first tool
        acc.update_from_parsed(
            self._make_parsed(content_block_stopped_index=0),
            "temp_1",
        )
        assert 0 not in acc._streaming_tool_blocks
        assert 1 in acc._streaming_tool_blocks

    def test_invalid_json_handled_gracefully(self):
        """Malformed JSON in tool input doesn't crash."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        acc.update_from_parsed(
            self._make_parsed(tool_use_started={"index": 0, "name": "mcp__action__excuse"}),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(input_json_delta='{"broken json'),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(content_block_stopped_index=0),
            "temp_1",
        )

        # Should not crash, no excuse reason captured
        assert acc.excuse_reasons == []

    def test_empty_reason_not_captured(self):
        """Excuse tool with empty reason doesn't produce an entry."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        acc.update_from_parsed(
            self._make_parsed(tool_use_started={"index": 0, "name": "mcp__action__excuse"}),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(input_json_delta='{"reason": ""}'),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(content_block_stopped_index=0),
            "temp_1",
        )

        assert acc.excuse_reasons == []

    def test_content_deltas_still_emitted(self):
        """Content and thinking deltas still produce events during tool streaming."""
        from domain.streaming import ContentDeltaEvent, ResponseAccumulator, ThinkingDeltaEvent

        acc = ResponseAccumulator()

        # Text delta should still produce events
        parsed = self._make_parsed(response_text="hello")
        events = acc.update_from_parsed(parsed, "temp_1")

        assert len(events) == 1
        assert isinstance(events[0], ContentDeltaEvent)
        assert events[0].delta == "hello"

        # Thinking delta
        parsed = self._make_parsed(response_text="hello", thinking_text="hmm")
        events = acc.update_from_parsed(parsed, "temp_1")

        assert len(events) == 1
        assert isinstance(events[0], ThinkingDeltaEvent)
        assert events[0].delta == "hmm"

    def test_excuse_in_end_event(self):
        """Excuse reasons appear in the final StreamEndEvent."""
        from domain.streaming import ResponseAccumulator

        acc = ResponseAccumulator()

        # Simulate excuse tool streaming
        acc.update_from_parsed(
            self._make_parsed(tool_use_started={"index": 0, "name": "mcp__action__excuse"}),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(input_json_delta='{"reason": "secretly happy"}'),
            "temp_1",
        )
        acc.update_from_parsed(
            self._make_parsed(content_block_stopped_index=0),
            "temp_1",
        )

        end = acc.create_end_event("temp_1")
        assert end.excuse_reasons == ["secretly happy"]
