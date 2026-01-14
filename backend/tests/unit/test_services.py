"""
Unit tests for cleanup operations and config I/O.

Tests cleanup functions that coordinate between CRUD and other components,
and agent configuration I/O operations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from config import AgentConfigIO
from crud import (
    clear_room_messages_with_cleanup,
    delete_agent_with_cleanup,
    delete_room_with_cleanup,
    remove_agent_from_room_with_cleanup,
)
from domain.task_identifier import TaskIdentifier


class TestAgentService:
    """Tests for agent service operations."""

    @pytest.mark.unit
    async def test_delete_agent_with_cleanup(self, test_db, sample_agent):
        """Test deleting an agent with cleanup."""
        # Mock agent manager with ClientPool
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.get_keys_for_agent = MagicMock(
            return_value=[
                TaskIdentifier(room_id=1, agent_id=sample_agent.id),
                TaskIdentifier(room_id=2, agent_id=sample_agent.id),
            ]
        )
        agent_manager.client_pool.cleanup = AsyncMock()

        # Delete agent
        result = await delete_agent_with_cleanup(test_db, sample_agent.id, agent_manager)

        assert result is True
        # Should cleanup 2 clients (room_1 and room_2 for this agent)
        assert agent_manager.client_pool.cleanup.call_count == 2

    @pytest.mark.unit
    async def test_delete_agent_with_cleanup_not_found(self, test_db):
        """Test deleting a non-existent agent."""
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.cleanup = AsyncMock()

        result = await delete_agent_with_cleanup(test_db, 999, agent_manager)

        assert result is False
        # Should not attempt cleanup
        agent_manager.client_pool.cleanup.assert_not_called()

    @pytest.mark.unit
    async def test_remove_agent_from_room_with_cleanup(self, test_db, sample_room_with_agents, sample_agent):
        """Test removing an agent from a room with cleanup."""
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.cleanup = AsyncMock()

        result = await remove_agent_from_room_with_cleanup(
            test_db, sample_room_with_agents.id, sample_agent.id, agent_manager
        )

        assert result is True
        # Should cleanup the specific client
        agent_manager.client_pool.cleanup.assert_called_once()

    @pytest.mark.unit
    async def test_delete_room_with_cleanup(self, test_db, sample_room_with_agents, sample_agent):
        """Test deleting a room with cleanup."""
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.cleanup = AsyncMock()

        chat_orchestrator = MagicMock()
        chat_orchestrator.cleanup_room_state = AsyncMock()

        result = await delete_room_with_cleanup(test_db, sample_room_with_agents.id, agent_manager, chat_orchestrator)

        assert result is True
        # Should cleanup orchestrator and clients
        chat_orchestrator.cleanup_room_state.assert_called_once()
        agent_manager.client_pool.cleanup.assert_called_once()

    @pytest.mark.unit
    async def test_delete_room_without_orchestrator(self, test_db, sample_room_with_agents):
        """Test deleting a room without orchestrator."""
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.cleanup = AsyncMock()

        result = await delete_room_with_cleanup(
            test_db,
            sample_room_with_agents.id,
            agent_manager,
            None,  # No orchestrator
        )

        assert result is True

    @pytest.mark.unit
    async def test_clear_room_messages_with_cleanup(
        self, test_db, sample_room_with_agents, sample_agent, sample_message
    ):
        """Test clearing room messages with cleanup."""
        agent_manager = MagicMock()
        agent_manager.client_pool = MagicMock()
        agent_manager.client_pool.cleanup = AsyncMock()

        chat_orchestrator = MagicMock()
        chat_orchestrator.interrupt_room_processing = AsyncMock()

        result = await clear_room_messages_with_cleanup(
            test_db, sample_room_with_agents.id, agent_manager, chat_orchestrator
        )

        assert result is True
        # Should interrupt and cleanup
        chat_orchestrator.interrupt_room_processing.assert_called_once()
        agent_manager.client_pool.cleanup.assert_called_once()


class TestAgentConfigIO:
    """Tests for agent configuration service."""

    @pytest.mark.unit
    def test_load_agent_config_folder_structure(self, temp_agent_config):
        """Test loading agent config from folder structure."""
        config = AgentConfigIO.load_agent_config(str(temp_agent_config))

        assert config is not None
        assert config.in_a_nutshell == "Test agent nutshell"
        assert config.characteristics == "Test characteristics"
        assert config.recent_events == "Test recent events"
        # Verify the config is an AgentConfigData object
        assert hasattr(config, "in_a_nutshell")
        assert hasattr(config, "characteristics")
        assert hasattr(config, "recent_events")

    @pytest.mark.unit
    def test_load_agent_config_nonexistent(self):
        """Test loading non-existent agent config."""
        config = AgentConfigIO.load_agent_config("nonexistent/path")

        assert config is None
