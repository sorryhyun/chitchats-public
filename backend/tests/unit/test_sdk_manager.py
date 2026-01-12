"""
Unit tests for SDK AgentManager.

Tests agent manager functionality including client pooling,
interruption handling, and response generation.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from domain.agent_config import AgentConfigData
from domain.contexts import AgentResponseContext
from domain.task_identifier import TaskIdentifier
from providers.claude.options import build_agent_options
from sdk.client_pool import ClientPool
from sdk.manager import AgentManager


class TestAgentManagerInit:
    """Tests for AgentManager initialization."""

    def test_init_creates_empty_state(self):
        """Test that AgentManager initializes with empty state."""
        manager = AgentManager()

        assert manager.active_clients == {}
        assert isinstance(manager.client_pool, ClientPool)
        assert manager.client_pool.pool == {}


class TestInterruptAll:
    """Tests for interrupt_all method."""

    @pytest.mark.asyncio
    async def test_interrupt_all_with_clients(self):
        """Test interrupting all active clients."""
        manager = AgentManager()

        # Create mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        manager.active_clients = {
            TaskIdentifier(room_id=1, agent_id=1): mock_client1,
            TaskIdentifier(room_id=1, agent_id=2): mock_client2,
        }

        await manager.interrupt_all()

        # Verify both clients were interrupted
        mock_client1.interrupt.assert_awaited_once()
        mock_client2.interrupt.assert_awaited_once()

        # Verify active_clients was cleared
        assert manager.active_clients == {}

    @pytest.mark.asyncio
    async def test_interrupt_all_with_no_clients(self):
        """Test interrupt_all with no active clients."""
        manager = AgentManager()

        # Should not raise any errors
        await manager.interrupt_all()

        assert manager.active_clients == {}

    @pytest.mark.asyncio
    async def test_interrupt_all_handles_errors(self):
        """Test that interrupt_all handles client errors gracefully."""
        manager = AgentManager()

        # Create mock client that raises error on interrupt
        mock_client = AsyncMock()
        mock_client.interrupt.side_effect = Exception("Interrupt failed")

        manager.active_clients = {TaskIdentifier(room_id=1, agent_id=1): mock_client}

        # Should not raise - error is logged
        await manager.interrupt_all()

        # Active clients still cleared despite error
        assert manager.active_clients == {}


class TestInterruptRoom:
    """Tests for interrupt_room method."""

    @pytest.mark.asyncio
    async def test_interrupt_room_with_matching_clients(self):
        """Test interrupting clients in a specific room."""
        manager = AgentManager()

        # Create mock clients for different rooms
        mock_client_room1 = AsyncMock()
        mock_client_room2 = AsyncMock()

        manager.active_clients = {
            TaskIdentifier(room_id=1, agent_id=1): mock_client_room1,
            TaskIdentifier(room_id=2, agent_id=1): mock_client_room2,
        }

        await manager.interrupt_room(1)

        # Only room 1 client should be interrupted
        mock_client_room1.interrupt.assert_awaited_once()
        mock_client_room2.interrupt.assert_not_awaited()

        # Only room 1 task should be removed
        assert TaskIdentifier(room_id=1, agent_id=1) not in manager.active_clients
        assert TaskIdentifier(room_id=2, agent_id=1) in manager.active_clients

    @pytest.mark.asyncio
    async def test_interrupt_room_with_no_matching_clients(self):
        """Test interrupt_room when no clients match the room."""
        manager = AgentManager()

        mock_client = AsyncMock()
        manager.active_clients = {TaskIdentifier(room_id=2, agent_id=1): mock_client}

        await manager.interrupt_room(1)

        # Client should not be interrupted
        mock_client.interrupt.assert_not_awaited()
        assert TaskIdentifier(room_id=2, agent_id=1) in manager.active_clients


class TestBuildAgentOptions:
    """Tests for build_agent_options function."""

    def test_build_agent_options_basic(self):
        """Test building basic agent options."""
        config = AgentConfigData(in_a_nutshell="Test agent", characteristics="Friendly", recent_events="Recent event")

        context = Mock(agent_name="TestAgent", config=config, session_id=None, has_situation_builder=False)

        with (
            patch("sdk.options_builder.create_guidelines_mcp_server") as mock_guidelines_mcp,
            patch("sdk.options_builder.create_action_mcp_server") as mock_action_mcp,
        ):
            mock_guidelines_mcp.return_value = Mock()
            mock_action_mcp.return_value = Mock()

            options = build_agent_options(context, "System prompt")

            # Verify options were created correctly
            assert options.system_prompt == "System prompt"
            # Model is hardcoded to opus in options_builder.py
            assert "claude-opus" in options.model
            assert options.max_thinking_tokens == 32768
            assert "guidelines" in options.mcp_servers
            assert "action" in options.mcp_servers

    def test_build_agent_options_with_session(self):
        """Test building options with session ID."""
        config = AgentConfigData(in_a_nutshell="Test")
        context = Mock(
            agent_name="TestAgent", config=config, session_id="test_session_123", has_situation_builder=False
        )

        with (
            patch("sdk.options_builder.create_guidelines_mcp_server"),
            patch("sdk.options_builder.create_action_mcp_server"),
        ):
            options = build_agent_options(context, "System prompt")

            # Should include resume session
            assert options.resume == "test_session_123"


class TestGenerateSDKResponse:
    """Tests for generate_sdk_response async generator."""

    @pytest.mark.asyncio
    async def test_generate_response_basic_flow(self):
        """Test basic response generation flow."""
        manager = AgentManager()

        config = AgentConfigData(in_a_nutshell="Test")
        context = AgentResponseContext(
            system_prompt="Test prompt",
            user_message="Hello",
            agent_name="TestAgent",
            config=config,
            room_id=1,
            agent_id=1,
            session_id=None,
            task_id=TaskIdentifier(room_id=1, agent_id=1),
        )

        # Mock client
        mock_client = AsyncMock()

        # Mock streaming response
        async def mock_receive_response():
            # Simulate streaming messages
            # Text message
            text_msg = Mock()
            text_msg.text = "Hello"
            del text_msg.content
            yield text_msg

            # System message with session ID
            system_msg = Mock()
            system_msg.__class__.__name__ = "SystemMessage"
            system_msg.data = {"session_id": "session123"}
            del system_msg.text
            del system_msg.content
            yield system_msg

        mock_client.receive_response = mock_receive_response
        mock_client.query = AsyncMock()

        with (
            patch.object(manager.client_pool, "get_or_create", return_value=(mock_client, True)),
            patch("sdk.manager.write_debug_log"),
            patch("sdk.manager.append_response_to_debug_log"),
        ):
            events = []
            async for event in manager.generate_sdk_response(context):
                events.append(event)

            # Should have stream_start and stream_end events
            assert events[0]["type"] == "stream_start"
            assert events[-1]["type"] == "stream_end"
            assert events[-1]["session_id"] == "session123"

            # Client should be registered and unregistered
            assert TaskIdentifier(room_id=1, agent_id=1) not in manager.active_clients

    @pytest.mark.asyncio
    async def test_generate_response_handles_cancellation(self):
        """Test response generation handles cancellation."""
        manager = AgentManager()

        config = AgentConfigData(in_a_nutshell="Test")
        context = AgentResponseContext(
            system_prompt="Test prompt",
            user_message="Hello",
            agent_name="TestAgent",
            config=config,
            room_id=1,
            agent_id=1,
            task_id=TaskIdentifier(room_id=1, agent_id=1),
        )

        mock_client = AsyncMock()

        # Mock streaming that raises CancelledError
        async def mock_receive_response():
            raise asyncio.CancelledError()
            yield  # Never reached

        mock_client.receive_response = mock_receive_response
        mock_client.query = AsyncMock()

        with (
            patch.object(manager.client_pool, "get_or_create", return_value=(mock_client, True)),
            patch("sdk.manager.write_debug_log"),
            patch("sdk.manager.append_response_to_debug_log"),
        ):
            events = []
            async for event in manager.generate_sdk_response(context):
                events.append(event)

            # Should yield stream_end with skipped=True
            assert events[-1]["type"] == "stream_end"
            assert events[-1]["skipped"] is True

    @pytest.mark.asyncio
    async def test_generate_response_handles_errors(self):
        """Test response generation handles errors gracefully."""
        manager = AgentManager()

        config = AgentConfigData(in_a_nutshell="Test")
        context = AgentResponseContext(
            system_prompt="Test prompt",
            user_message="Hello",
            agent_name="TestAgent",
            config=config,
            room_id=1,
            agent_id=1,
            task_id=TaskIdentifier(room_id=1, agent_id=1),
        )

        mock_client = AsyncMock()

        # Mock client that raises error
        mock_client.query.side_effect = Exception("Connection error")

        with (
            patch.object(manager.client_pool, "get_or_create", return_value=(mock_client, True)),
            patch("sdk.manager.write_debug_log"),
            patch("sdk.manager.append_response_to_debug_log"),
        ):
            events = []
            async for event in manager.generate_sdk_response(context):
                events.append(event)

            # Should yield error in stream_end
            assert events[-1]["type"] == "stream_end"
            assert "Error" in events[-1]["response_text"]
