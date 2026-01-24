"""
Unit tests for ChatOrchestrator.

Tests multi-agent conversation orchestration logic.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from domain.task_identifier import TaskIdentifier
from chatroom_orchestration.critic import process_critic_feedback
from chatroom_orchestration.orchestrator import MAX_FOLLOW_UP_ROUNDS, MAX_TOTAL_MESSAGES, ChatOrchestrator


class TestChatOrchestratorInit:
    """Tests for ChatOrchestrator initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        orchestrator = ChatOrchestrator()

        assert orchestrator.max_follow_up_rounds == MAX_FOLLOW_UP_ROUNDS
        assert orchestrator.max_total_messages == MAX_TOTAL_MESSAGES
        assert orchestrator.active_room_tasks == {}
        assert orchestrator.last_user_message_time == {}
        assert orchestrator.response_generator is not None

    def test_init_with_custom_limits(self):
        """Test initialization with custom limits."""
        orchestrator = ChatOrchestrator(max_follow_up_rounds=3, max_total_messages=20)

        assert orchestrator.max_follow_up_rounds == 3
        assert orchestrator.max_total_messages == 20


class TestGetChattingAgents:
    """Tests for get_chatting_agents method."""

    def test_get_chatting_agents_with_active_clients(self):
        """Test retrieving list of chatting agents."""
        orchestrator = ChatOrchestrator()
        mock_manager = Mock()
        mock_manager.active_clients = {
            TaskIdentifier(room_id=1, agent_id=10): Mock(),
            TaskIdentifier(room_id=1, agent_id=20): Mock(),
            TaskIdentifier(room_id=2, agent_id=30): Mock(),
        }

        chatting_agents = orchestrator.get_chatting_agents(1, mock_manager)

        # Should return agents for room 1 only
        assert sorted(chatting_agents) == [10, 20]

    def test_get_chatting_agents_with_no_active_clients(self):
        """Test with no active clients."""
        orchestrator = ChatOrchestrator()
        mock_manager = Mock()
        mock_manager.active_clients = {}

        chatting_agents = orchestrator.get_chatting_agents(1, mock_manager)

        assert chatting_agents == []

    def test_get_chatting_agents_filters_by_room(self):
        """Test that only agents from the specified room are returned."""
        orchestrator = ChatOrchestrator()
        mock_manager = Mock()
        mock_manager.active_clients = {
            TaskIdentifier(room_id=1, agent_id=10): Mock(),
            TaskIdentifier(room_id=2, agent_id=20): Mock(),
            TaskIdentifier(room_id=3, agent_id=30): Mock(),
        }

        chatting_agents = orchestrator.get_chatting_agents(1, mock_manager)

        # Should only include agents from room 1
        assert chatting_agents == [10]


class TestInterruptRoomProcessing:
    """Tests for interrupt_room_processing method."""

    @pytest.mark.asyncio
    async def test_interrupt_room_with_active_task(self):
        """Test interrupting a room with an active task."""
        orchestrator = ChatOrchestrator()
        mock_manager = AsyncMock()

        # Create a real asyncio.Task that we can cancel
        async def long_running_task():
            # Simulate a long-running task that waits indefinitely
            await asyncio.sleep(100)

        mock_task = asyncio.create_task(long_running_task())
        orchestrator.active_room_tasks[1] = mock_task

        await orchestrator.interrupt_room_processing(1, mock_manager)

        # Task should be cancelled
        assert mock_task.cancelled()

        # Should interrupt agents via manager
        mock_manager.interrupt_room.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_interrupt_room_with_no_active_task(self):
        """Test interrupting a room with no active task."""
        orchestrator = ChatOrchestrator()
        mock_manager = AsyncMock()

        await orchestrator.interrupt_room_processing(1, mock_manager)

        # Should still call interrupt_room on manager
        mock_manager.interrupt_room.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_interrupt_room_with_completed_task(self):
        """Test interrupting a room where task is already done."""
        orchestrator = ChatOrchestrator()
        mock_manager = AsyncMock()

        # Create a completed task
        mock_task = AsyncMock()
        mock_task.done.return_value = True
        orchestrator.active_room_tasks[1] = mock_task

        await orchestrator.interrupt_room_processing(1, mock_manager)

        # Should not try to cancel completed task
        mock_task.cancel.assert_not_called()


class TestCleanupRoomState:
    """Tests for cleanup_room_state method."""

    @pytest.mark.asyncio
    async def test_cleanup_room_state_complete(self):
        """Test complete room state cleanup."""
        orchestrator = ChatOrchestrator()
        mock_manager = AsyncMock()

        # Setup room state
        orchestrator.active_room_tasks[1] = AsyncMock()
        orchestrator.last_user_message_time[1] = 123.456

        with patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()) as mock_interrupt:
            await orchestrator.cleanup_room_state(1, mock_manager)

            # Should interrupt processing (with save_partial_responses=False for cleanup)
            mock_interrupt.assert_awaited_once_with(1, mock_manager, save_partial_responses=False)

        # Should remove from tracking dicts
        assert 1 not in orchestrator.active_room_tasks
        assert 1 not in orchestrator.last_user_message_time

    @pytest.mark.asyncio
    async def test_cleanup_room_state_partial(self):
        """Test cleanup when only some state exists."""
        orchestrator = ChatOrchestrator()
        mock_manager = AsyncMock()

        # Only last_user_message_time exists
        orchestrator.last_user_message_time[1] = 123.456

        with patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()):
            await orchestrator.cleanup_room_state(1, mock_manager)

        # Should not raise errors
        assert 1 not in orchestrator.last_user_message_time


class TestHandleUserMessage:
    """Tests for handle_user_message method."""

    @pytest.mark.asyncio
    async def test_handle_user_message_saves_message(self):
        """Test that user message is saved to database."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_manager = None  # No broadcasting
        mock_agent_manager = AsyncMock()

        message_data = {"content": "Hello agents!", "participant_type": "user", "participant_name": None}

        # Mock saved message
        saved_message = Mock(id=1, content="Hello agents!", role="user", timestamp=Mock())

        with (
            patch("orchestration.orchestrator.crud.create_message", return_value=saved_message) as mock_create,
            patch("orchestration.orchestrator.crud.get_agents", return_value=[]) as mock_get_agents,
            patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()),
        ):
            await orchestrator.handle_user_message(
                db=mock_db,
                room_id=1,
                message_data=message_data,
                _manager=mock_manager,
                agent_manager=mock_agent_manager,
            )

            # Should save message
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_user_message_uses_saved_message_id(self):
        """Test using pre-saved message ID."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_manager = None
        mock_agent_manager = AsyncMock()

        # Mock database get
        saved_message = Mock(id=123, content="Hello", role="user")
        mock_db.get.return_value = saved_message

        message_data = {"content": "Hello"}

        with (
            patch("orchestration.orchestrator.crud.create_message") as mock_create,
            patch("orchestration.orchestrator.crud.get_agents", return_value=[]),
            patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()),
        ):
            await orchestrator.handle_user_message(
                db=mock_db,
                room_id=1,
                message_data=message_data,
                _manager=mock_manager,
                agent_manager=mock_agent_manager,
                saved_user_message_id=123,
            )

            # Should NOT create new message
            mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_user_message_interrupts_previous_processing(self):
        """Test that previous processing is interrupted."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_manager = None
        mock_agent_manager = AsyncMock()

        message_data = {"content": "New message"}
        saved_message = Mock(id=1, content="New message", role="user", timestamp=Mock())

        with (
            patch("orchestration.orchestrator.crud.create_message", return_value=saved_message),
            patch("orchestration.orchestrator.crud.get_agents", return_value=[]),
            patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()) as mock_interrupt,
        ):
            await orchestrator.handle_user_message(
                db=mock_db,
                room_id=1,
                message_data=message_data,
                _manager=mock_manager,
                agent_manager=mock_agent_manager,
            )

            # Should interrupt existing processing (with db for saving partial responses)
            mock_interrupt.assert_awaited_once_with(1, mock_agent_manager, db=mock_db)

    @pytest.mark.asyncio
    async def test_handle_user_message_records_timestamp(self):
        """Test that user message timestamp is recorded."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_manager = None
        mock_agent_manager = AsyncMock()

        message_data = {"content": "Hello"}
        saved_message = Mock(id=1, content="Hello", role="user", timestamp=Mock())

        with (
            patch("orchestration.orchestrator.crud.create_message", return_value=saved_message),
            patch("orchestration.orchestrator.crud.get_agents", return_value=[]),
            patch.object(orchestrator, "interrupt_room_processing", new=AsyncMock()),
        ):
            await orchestrator.handle_user_message(
                db=mock_db,
                room_id=1,
                message_data=message_data,
                _manager=mock_manager,
                agent_manager=mock_agent_manager,
            )

            # Should record timestamp
            assert 1 in orchestrator.last_user_message_time
            assert isinstance(orchestrator.last_user_message_time[1], float)


class TestProcessAgentResponses:
    """Tests for _process_agent_responses method with tape-based scheduling."""

    @pytest.mark.asyncio
    async def test_process_agent_responses_uses_tape_system(self):
        """Test that tape-based scheduling is used for agent responses."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_agent_manager = AsyncMock()
        mock_orch_context = Mock(db=mock_db, room_id=1, agent_manager=mock_agent_manager)

        # Mock agents with required attributes
        mock_agent1 = Mock(id=1, name="Alice", priority=0, interrupt_every_turn=0, transparent=0)
        mock_agent2 = Mock(id=2, name="Bob", priority=0, interrupt_every_turn=0, transparent=0)

        # Mock tape execution result
        mock_result = Mock(
            was_paused=False,
            was_interrupted=False,
            reached_limit=False,
            all_skipped=False,
            total_responses=2,
        )

        with (
            patch("orchestration.orchestrator.TapeGenerator") as mock_generator_class,
            patch("orchestration.orchestrator.TapeExecutor") as mock_executor_class,
        ):
            mock_generator = Mock()
            mock_tape = Mock()
            mock_generator.generate_initial_round.return_value = mock_tape
            mock_generator.generate_follow_up_round.return_value = mock_tape
            mock_generator_class.return_value = mock_generator

            mock_executor = Mock()
            mock_executor.execute = AsyncMock(return_value=mock_result)
            mock_executor_class.return_value = mock_executor

            await orchestrator._process_agent_responses(
                orch_context=mock_orch_context,
                agents=[mock_agent1, mock_agent2],
                interrupt_agents=[],
                final_response_agents=[],
                critic_agents=[],
                user_message_content="Hello",
            )

            # Should create tape generator and executor
            mock_generator_class.assert_called_once()
            mock_executor_class.assert_called_once()

            # Should generate and execute initial tape
            mock_generator.generate_initial_round.assert_called_once()
            mock_executor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_process_agent_responses_skips_follow_up_with_one_agent(self):
        """Test that follow-up rounds are skipped with only one agent."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_agent_manager = AsyncMock()
        mock_orch_context = Mock(db=mock_db, room_id=1, agent_manager=mock_agent_manager)

        # Single agent
        mock_agent = Mock(id=1, name="Alice", priority=0, interrupt_every_turn=0, transparent=0)

        # Initial round succeeds, but only 1 agent
        mock_result = Mock(
            was_paused=False,
            was_interrupted=False,
            reached_limit=False,
            all_skipped=False,
            total_responses=1,
        )

        with (
            patch("orchestration.orchestrator.TapeGenerator") as mock_generator_class,
            patch("orchestration.orchestrator.TapeExecutor") as mock_executor_class,
        ):
            mock_generator = Mock()
            mock_tape = Mock()
            mock_generator.generate_initial_round.return_value = mock_tape
            mock_generator_class.return_value = mock_generator

            mock_executor = Mock()
            mock_executor.execute = AsyncMock(return_value=mock_result)
            mock_executor_class.return_value = mock_executor

            await orchestrator._process_agent_responses(
                orch_context=mock_orch_context,
                agents=[mock_agent],  # Only one agent
                interrupt_agents=[],
                final_response_agents=[],
                critic_agents=[],
                user_message_content="Hello",
            )

            # Should only call initial round, not follow-up rounds
            mock_generator.generate_initial_round.assert_called_once()
            mock_generator.generate_follow_up_round.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_agent_responses_processes_critics(self):
        """Test that critic agents are processed after tape execution."""
        orchestrator = ChatOrchestrator()
        mock_db = AsyncMock()
        mock_agent_manager = AsyncMock()
        mock_orch_context = Mock(db=mock_db, room_id=1, agent_manager=mock_agent_manager)

        mock_agent = Mock(id=1, name="Alice", priority=0, interrupt_every_turn=0, transparent=0)
        mock_critic = Mock(id=2, name="Critic", is_critic=True)

        mock_result = Mock(
            was_paused=False,
            was_interrupted=False,
            reached_limit=False,
            all_skipped=False,
            total_responses=1,
        )

        with (
            patch("orchestration.orchestrator.TapeGenerator") as mock_generator_class,
            patch("orchestration.orchestrator.TapeExecutor") as mock_executor_class,
            patch("orchestration.orchestrator.process_critic_feedback", new=AsyncMock()) as mock_critics,
        ):
            mock_generator = Mock()
            mock_tape = Mock()
            mock_generator.generate_initial_round.return_value = mock_tape
            mock_generator_class.return_value = mock_generator

            mock_executor = Mock()
            mock_executor.execute = AsyncMock(return_value=mock_result)
            mock_executor_class.return_value = mock_executor

            await orchestrator._process_agent_responses(
                orch_context=mock_orch_context,
                agents=[mock_agent],
                interrupt_agents=[],
                final_response_agents=[],
                critic_agents=[mock_critic],
                user_message_content="Hello",
            )

            # Should process critics
            mock_critics.assert_awaited_once()


class TestProcessCriticFeedback:
    """Tests for process_critic_feedback function."""

    @pytest.mark.asyncio
    async def test_process_critic_feedback_concurrent(self):
        """Test that critics process concurrently."""
        mock_orch_context = Mock()
        mock_response_generator = Mock()
        mock_response_generator.generate_response = AsyncMock(return_value=True)

        critics = [Mock(id=i, name=f"Critic{i}") for i in range(3)]

        await process_critic_feedback(
            orch_context=mock_orch_context,
            critic_agents=critics,
            user_message_content="Hello",
            response_generator=mock_response_generator,
        )

        # Should call generate_response for each critic with is_critic=True
        assert mock_response_generator.generate_response.await_count == 3

        # Verify is_critic flag was set
        for call in mock_response_generator.generate_response.await_args_list:
            assert call[1]["is_critic"] is True

    @pytest.mark.asyncio
    async def test_process_critic_feedback_handles_errors(self):
        """Test that critic errors don't stop other critics."""
        mock_orch_context = Mock()
        mock_response_generator = Mock()

        critics = [Mock(id=1, name="Critic1"), Mock(id=2, name="Critic2")]

        # First critic raises error, second succeeds
        mock_response_generator.generate_response = AsyncMock(side_effect=[Exception("Critic error"), True])

        # Should not raise exception
        await process_critic_feedback(
            orch_context=mock_orch_context,
            critic_agents=critics,
            user_message_content="Hello",
            response_generator=mock_response_generator,
        )

        # Both critics should have been processed
        assert mock_response_generator.generate_response.await_count == 2
