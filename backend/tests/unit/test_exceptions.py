"""
Unit tests for custom exception classes.

Tests exception initialization and error messages.
"""

import pytest
from core.exceptions import AgentNotFoundError, ConfigurationError, RoomAlreadyExistsError, RoomNotFoundError
from fastapi import status


class TestRoomExceptions:
    """Tests for room-related exceptions."""

    @pytest.mark.unit
    def test_room_already_exists_error(self):
        """Test RoomAlreadyExistsError exception."""
        room_name = "Test Room"
        error = RoomAlreadyExistsError(room_name)

        assert error.status_code == status.HTTP_409_CONFLICT
        assert room_name in error.detail
        assert "already exists" in error.detail

    @pytest.mark.unit
    def test_room_not_found_error(self):
        """Test RoomNotFoundError exception."""
        room_id = 123
        error = RoomNotFoundError(room_id)

        assert error.status_code == status.HTTP_404_NOT_FOUND
        assert str(room_id) in error.detail
        assert "not found" in error.detail


class TestAgentExceptions:
    """Tests for agent-related exceptions."""

    @pytest.mark.unit
    def test_agent_not_found_error(self):
        """Test AgentNotFoundError exception."""
        agent_id = 456
        error = AgentNotFoundError(agent_id)

        assert error.status_code == status.HTTP_404_NOT_FOUND
        assert str(agent_id) in error.detail
        assert "not found" in error.detail


class TestConfigurationError:
    """Tests for ConfigurationError exception."""

    @pytest.mark.unit
    def test_configuration_error(self):
        """Test ConfigurationError exception."""
        message = "Invalid configuration"
        error = ConfigurationError(message)

        assert isinstance(error, ValueError)
        assert message in str(error)
        assert "Configuration error" in str(error)

    @pytest.mark.unit
    def test_configuration_error_can_be_raised(self):
        """Test that ConfigurationError can be raised and caught."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("Test error message")

        assert "Test error message" in str(exc_info.value)
