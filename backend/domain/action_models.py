"""
Action tool models for MCP tool inputs and outputs.

This module defines Pydantic models for action tool (skip, memorize, recall)
inputs and outputs, providing type-safe validation and structured data.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# Input Models
class SkipInput(BaseModel):
    """Input model for skip tool - takes no arguments."""

    pass


class MemorizeInput(BaseModel):
    """Input model for memorize tool."""

    memory_entry: str = Field(..., min_length=1, description="The memory entry to record")

    @field_validator("memory_entry")
    @classmethod
    def validate_memory_entry(cls, v: str) -> str:
        """Ensure memory entry is not just whitespace."""
        if not v.strip():
            raise ValueError("Memory entry cannot be empty or whitespace")
        return v.strip()


class RecallInput(BaseModel):
    """Input model for recall tool."""

    subtitle: str = Field(..., min_length=1, description="The memory subtitle to retrieve")

    @field_validator("subtitle")
    @classmethod
    def validate_subtitle(cls, v: str) -> str:
        """Ensure subtitle is not just whitespace."""
        if not v.strip():
            raise ValueError("Subtitle cannot be empty or whitespace")
        return v.strip()


# Output Models
class ToolResponse(BaseModel):
    """Base model for tool responses."""

    content: list[dict[str, str]] = Field(default_factory=list)


class SkipOutput(BaseModel):
    """Output model for skip tool."""

    response: str = Field(..., description="Confirmation message for skip action")

    def to_tool_response(self) -> dict[str, Any]:
        """Convert to MCP tool response format."""
        return {"content": [{"type": "text", "text": self.response}]}


class MemorizeOutput(BaseModel):
    """Output model for memorize tool."""

    response: str = Field(..., description="Confirmation message with the memorized entry")
    memory_entry: str = Field(..., description="The memory entry that was recorded")

    def to_tool_response(self) -> dict[str, Any]:
        """Convert to MCP tool response format."""
        return {"content": [{"type": "text", "text": self.response}]}


class RecallOutput(BaseModel):
    """Output model for recall tool."""

    response: str = Field(..., description="The retrieved memory content or error message")
    success: bool = Field(..., description="Whether the memory was found")
    subtitle: str = Field(..., description="The subtitle that was queried")
    memory_content: Optional[str] = Field(None, description="The full memory content if found")

    def to_tool_response(self) -> dict[str, Any]:
        """Convert to MCP tool response format."""
        return {"content": [{"type": "text", "text": self.response}]}


# =============================================================================
# Guideline Tool Input Models
# =============================================================================


class GuidelinesReadInput(BaseModel):
    """Input model for guidelines read tool - takes no arguments."""

    pass


class GuidelinesAnthropicInput(BaseModel):
    """Input model for guidelines anthropic tool."""

    situation: str = Field(
        ...,
        min_length=1,
        description="Brief description of the situation (e.g., 'Characters are talking about a detailed method for creating a chemical weapon')",
    )

    @field_validator("situation")
    @classmethod
    def validate_situation(cls, v: str) -> str:
        """Ensure situation is not just whitespace."""
        if not v.strip():
            raise ValueError("Situation description cannot be empty or whitespace")
        return v.strip()
