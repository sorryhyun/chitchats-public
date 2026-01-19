"""
Etc tool models for MCP tool inputs and outputs.

This module defines Pydantic models for utility tools (current_time, etc.)
inputs and outputs, providing type-safe validation and structured data.
"""

from typing import Any

from pydantic import BaseModel, Field


# Input Models
class CurrentTimeInput(BaseModel):
    """Input model for current_time tool - takes no arguments."""

    pass


# Output Models
class CurrentTimeOutput(BaseModel):
    """Output model for current_time tool."""

    response: str = Field(..., description="Formatted current time response")
    current_time: str = Field(..., description="The current time in ISO format")

    def to_tool_response(self) -> dict[str, Any]:
        """Convert to MCP tool response format."""
        return {"content": [{"type": "text", "text": self.response}]}
