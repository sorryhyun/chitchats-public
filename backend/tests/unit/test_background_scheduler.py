"""
Unit tests for BackgroundScheduler.

Tests background processing of autonomous agent conversations.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from infrastructure.scheduler import BackgroundScheduler


class SessionFactory:
    """Helper to track async session creation and closure."""

    def __init__(self):
        self.created = 0
        self.closed = 0
        self.sessions = []

    async def __call__(self):
        self.created += 1
        session = AsyncMock()
        self.sessions.append(session)
        try:
            yield session
        finally:
            self.closed += 1


class TestBackgroundSchedulerInit:
    """Tests for BackgroundScheduler initialization."""

    def test_init(self):
        """Test initialization."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        assert scheduler.chat_orchestrator == mock_orchestrator
        assert scheduler.agent_manager == mock_agent_manager
        assert scheduler.get_db_session == mock_get_db
        assert scheduler.max_concurrent_rooms == 5
        assert scheduler.is_running is False
        assert scheduler.scheduler is not None


class TestBackgroundSchedulerStart:
    """Tests for start method."""

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        with (
            patch.object(scheduler.scheduler, "start") as mock_start,
            patch.object(scheduler.scheduler, "add_job") as mock_add_job,
        ):
            scheduler.start()

            # Should add two jobs (process rooms + cleanup cache) and start scheduler
            assert mock_add_job.call_count == 2
            mock_start.assert_called_once()

            assert scheduler.is_running is True

    def test_start_scheduler_already_running(self):
        """Test that starting already-running scheduler is idempotent."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "start") as mock_start:
            scheduler.start()

            # Should not start again
            mock_start.assert_not_called()


class TestBackgroundSchedulerStop:
    """Tests for stop method."""

    def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

            # Should shutdown scheduler
            mock_shutdown.assert_called_once()
            assert scheduler.is_running is False

    def test_stop_scheduler_not_running(self):
        """Test stopping already-stopped scheduler."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)
        scheduler.is_running = False

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

            # Should not shutdown again
            mock_shutdown.assert_not_called()


class TestGetActiveRooms:
    """Tests for _get_active_rooms method."""

    @pytest.mark.asyncio
    async def test_get_active_rooms_with_multi_agent_rooms(self):
        """Test getting active rooms with multiple agents."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        # Mock database response
        mock_db = AsyncMock()
        mock_agent1 = Mock(is_critic=False)
        mock_agent2 = Mock(is_critic=False)
        mock_room = Mock(id=1, is_paused=False, agents=[mock_agent1, mock_agent2])

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_room]
        mock_db.execute.return_value = mock_result

        active_rooms = await scheduler._get_active_rooms(mock_db)

        # Should return room with 2+ agents
        assert len(active_rooms) == 1
        assert active_rooms[0].id == 1

    @pytest.mark.asyncio
    async def test_get_active_rooms_filters_single_agent_rooms(self):
        """Test that single-agent rooms are filtered out."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_agent = Mock(is_critic=False)
        mock_room = Mock(id=1, agents=[mock_agent])  # Only 1 agent

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_room]
        mock_db.execute.return_value = mock_result

        active_rooms = await scheduler._get_active_rooms(mock_db)

        # Should filter out single-agent room
        assert len(active_rooms) == 0

    @pytest.mark.asyncio
    async def test_get_active_rooms_excludes_critics(self):
        """Test that critic agents are excluded from count."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_agent = Mock(is_critic=False)
        mock_critic = Mock(is_critic=True)
        # Room has 1 regular agent + 1 critic = should be filtered
        mock_room = Mock(id=1, agents=[mock_agent, mock_critic])

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_room]
        mock_db.execute.return_value = mock_result

        active_rooms = await scheduler._get_active_rooms(mock_db)

        # Should filter out (only 1 non-critic agent)
        assert len(active_rooms) == 0


class TestCleanupCompletedTasks:
    """Tests for _cleanup_completed_tasks method."""

    def test_cleanup_completed_tasks(self):
        """Test cleaning up completed tasks."""
        mock_orchestrator = Mock()
        mock_orchestrator.active_room_tasks = {
            1: Mock(done=Mock(return_value=True)),
            2: Mock(done=Mock(return_value=False)),
            3: Mock(done=Mock(return_value=True)),
        }
        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        scheduler._cleanup_completed_tasks()

        # Should remove completed tasks (1 and 3)
        assert 1 not in mock_orchestrator.active_room_tasks
        assert 2 in mock_orchestrator.active_room_tasks
        assert 3 not in mock_orchestrator.active_room_tasks


class TestProcessRoomAutonomousRound:
    """Tests for _process_room_autonomous_round method."""

    @pytest.mark.asyncio
    async def test_process_room_autonomous_round_basic(self):
        """Test processing autonomous round with tape-based scheduling."""
        mock_orchestrator = Mock()
        mock_orchestrator.active_room_tasks = {}
        mock_orchestrator.max_total_messages = 30
        mock_orchestrator.response_generator = Mock()

        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_room = Mock(id=1, name="Test Room", max_interactions=None)
        # Create proper mock agents with required attributes
        mock_agent1 = Mock(id=1, name="Agent1", is_critic=False, priority=0, interrupt_every_turn=0, transparent=0)
        mock_agent2 = Mock(id=2, name="Agent2", is_critic=False, priority=0, interrupt_every_turn=0, transparent=0)

        # Mock the tape executor to return a successful result
        mock_execution_result = Mock(all_skipped=False, total_responses=1)

        with (
            patch(
                "infrastructure.scheduler.crud.get_agents_cached",
                new=AsyncMock(return_value=[mock_agent1, mock_agent2]),
            ),
            patch("infrastructure.scheduler.TapeExecutor") as mock_executor_class,
            patch("infrastructure.scheduler.TapeGenerator") as mock_generator_class,
        ):
            mock_executor = Mock()
            mock_executor.execute = AsyncMock(return_value=mock_execution_result)
            mock_executor_class.return_value = mock_executor

            mock_generator = Mock()
            mock_tape = Mock()
            mock_generator.generate_follow_up_round.return_value = mock_tape
            mock_generator_class.return_value = mock_generator

            await scheduler._process_room_autonomous_round(mock_db, mock_room)

            # Should generate and execute a follow-up tape
            mock_generator.generate_follow_up_round.assert_called_once_with(round_num=0)
            mock_executor.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_room_skips_if_already_processing(self):
        """Test skipping room that's already being processed."""
        mock_orchestrator = Mock()
        mock_orchestrator.active_room_tasks = {
            1: Mock(done=Mock(return_value=False))  # Room 1 is active
        }
        mock_orchestrator._follow_up_rounds = AsyncMock()

        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_room = Mock(id=1)

        await scheduler._process_room_autonomous_round(mock_db, mock_room)

        # Should not process
        mock_orchestrator._follow_up_rounds.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_room_skips_if_less_than_2_agents(self):
        """Test skipping room with less than 2 non-critic agents."""
        mock_orchestrator = Mock()
        mock_orchestrator.active_room_tasks = {}
        mock_orchestrator._count_agent_messages = AsyncMock(return_value=0)
        mock_orchestrator._follow_up_rounds = AsyncMock()

        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_room = Mock(id=1, name="Test Room", max_interactions=None)  # Set all required attributes
        mock_agent = Mock(is_critic=False)

        with patch("infrastructure.scheduler.crud.get_agents_cached", return_value=[mock_agent]):  # Only 1 agent
            await scheduler._process_room_autonomous_round(mock_db, mock_room)

            # Should not process
            mock_orchestrator._follow_up_rounds.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_room_skips_if_max_interactions_reached(self):
        """Test skipping room that reached max interactions."""
        mock_orchestrator = Mock()
        mock_orchestrator.active_room_tasks = {}
        mock_orchestrator.max_total_messages = 30
        mock_orchestrator.response_generator = Mock()

        mock_agent_manager = Mock()
        mock_get_db = Mock()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, mock_get_db)

        mock_db = AsyncMock()
        mock_room = Mock(id=1, name="Test Room", max_interactions=10)  # Already at limit
        mock_agent1 = Mock(id=1, name="Agent1", is_critic=False, priority=0, interrupt_every_turn=0, transparent=0)
        mock_agent2 = Mock(id=2, name="Agent2", is_critic=False, priority=0, interrupt_every_turn=0, transparent=0)

        with (
            patch(
                "infrastructure.scheduler.crud.get_agents_cached",
                new=AsyncMock(return_value=[mock_agent1, mock_agent2]),
            ),
            patch.object(scheduler, "_count_agent_messages", new=AsyncMock(return_value=10)),
            patch("infrastructure.scheduler.TapeExecutor") as mock_executor_class,
        ):
            mock_executor = Mock()
            mock_executor.execute = AsyncMock()
            mock_executor_class.return_value = mock_executor

            await scheduler._process_room_autonomous_round(mock_db, mock_room)

            # Should not process - tape executor should not be called
            mock_executor.execute.assert_not_awaited()


class TestProcessActiveRooms:
    """Tests for _process_active_rooms method."""

    @pytest.mark.asyncio
    async def test_process_active_rooms_with_no_rooms(self):
        """Test processing when no active rooms."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        session_factory = SessionFactory()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, session_factory)

        with (
            patch.object(scheduler, "_get_active_rooms", return_value=[]),
            patch.object(scheduler, "_process_room_autonomous_round", new=AsyncMock()) as mock_process,
        ):
            await scheduler._process_active_rooms()

            # Should not process any rooms
            mock_process.assert_not_awaited()
            assert session_factory.created == 1
            assert session_factory.closed == 1

    @pytest.mark.asyncio
    async def test_process_active_rooms_with_multiple_rooms(self):
        """Test processing multiple active rooms concurrently."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        session_factory = SessionFactory()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, session_factory)

        mock_rooms = [
            Mock(id=1, max_interactions=None),
            Mock(id=2, max_interactions=None),
            Mock(id=3, max_interactions=None),
        ]

        with (
            patch.object(scheduler, "_get_active_rooms", return_value=mock_rooms),
            patch.object(scheduler, "_process_room_autonomous_round", new=AsyncMock()) as mock_process,
        ):
            await scheduler._process_active_rooms()

            # Should process all rooms
            assert mock_process.await_count == 3
            # One session for room discovery, one per room
            assert session_factory.created == 4
            assert session_factory.closed == 4
            # Ensure each room uses its own session (after the first discovery session)
            discovery_session = session_factory.sessions[0]
            room_sessions = session_factory.sessions[1:]
            for call, room_session in zip(mock_process.await_args_list, room_sessions):
                assert call.args[0] is room_session
                assert call.args[0] is not discovery_session

    @pytest.mark.asyncio
    async def test_process_active_rooms_handles_errors(self):
        """Test that errors in one room don't affect others."""
        mock_orchestrator = Mock()
        mock_agent_manager = Mock()
        session_factory = SessionFactory()

        scheduler = BackgroundScheduler(mock_orchestrator, mock_agent_manager, session_factory)

        mock_rooms = [Mock(id=1, max_interactions=None), Mock(id=2, max_interactions=None)]

        # First room raises error, second succeeds
        async def mock_process_room(db, room):
            if room.id == 1:
                raise Exception("Processing error")

        with (
            patch.object(scheduler, "_get_active_rooms", return_value=mock_rooms),
            patch.object(scheduler, "_process_room_autonomous_round", side_effect=mock_process_room) as mock_process,
        ):
            # Should not raise exception
            await scheduler._process_active_rooms()

            assert session_factory.created == 3
            assert session_factory.closed == 3
            assert mock_process.await_count == 2
