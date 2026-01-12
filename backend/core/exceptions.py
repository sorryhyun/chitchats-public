"""
Custom exception classes for the ChitChats application.

These exceptions provide more specific error handling and better error messages
for common failure scenarios in the application.
"""

from fastapi import HTTPException, status


class RoomAlreadyExistsError(HTTPException):
    """Raised when attempting to create a room with a name that already exists."""

    def __init__(self, room_name: str):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=f"Room with name '{room_name}' already exists")


class RoomNotFoundError(HTTPException):
    """Raised when a requested room does not exist."""

    def __init__(self, room_id: int):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"Room with id {room_id} not found")


class AgentNotFoundError(HTTPException):
    """Raised when a requested agent does not exist."""

    def __init__(self, agent_id: int):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with id {agent_id} not found")


class ConfigurationError(ValueError):
    """Raised when there's an error in configuration parsing or validation."""

    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")
