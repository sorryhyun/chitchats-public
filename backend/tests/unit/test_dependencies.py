"""
Unit tests for FastAPI dependencies.

Tests dependency injection functions.
"""

from unittest.mock import MagicMock

import pytest
from core.dependencies import get_agent_manager, get_chat_orchestrator
from orchestration import ChatOrchestrator
from sdk import AgentManager


class TestDependencies:
    """Tests for dependency functions."""

    @pytest.mark.unit
    def test_get_agent_manager(self):
        """Test get_agent_manager returns AgentManager from app state."""
        # Create mock request with app state
        mock_agent_manager = MagicMock(spec=AgentManager)
        mock_app = MagicMock()  # Don't use spec for app to allow state attribute
        mock_app.state.agent_manager = mock_agent_manager

        mock_request = MagicMock()
        mock_request.app = mock_app

        manager = get_agent_manager(mock_request)

        assert manager is mock_agent_manager

    @pytest.mark.unit
    def test_get_chat_orchestrator(self):
        """Test get_chat_orchestrator returns ChatOrchestrator from app state."""
        # Create mock request with app state
        mock_orchestrator = MagicMock(spec=ChatOrchestrator)
        mock_app = MagicMock()  # Don't use spec for app to allow state attribute
        mock_app.state.chat_orchestrator = mock_orchestrator

        mock_request = MagicMock()
        mock_request.app = mock_app

        orchestrator = get_chat_orchestrator(mock_request)

        assert orchestrator is mock_orchestrator
