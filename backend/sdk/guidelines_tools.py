"""
Guidelines tools for agent behavioral guidance.

This module defines MCP tools for guidelines:
- read: Agents call mcp__guidelines__read to retrieve behavioral guidelines
- anthropic: Tool for flagging potentially harmful requests
"""

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from domain.action_models import GuidelinesAnthropicInput, GuidelinesReadInput

from .config import (
    get_extreme_traits,
    get_situation_builder_note,
    get_tool_description,
    get_tool_response,
    is_tool_enabled,
)


def _create_guidelines_read_tool(agent_name: str, guidelines_content: str):
    """Create callable read tool that returns behavioral guidelines."""
    description = get_tool_description("read", agent_name=agent_name)

    @tool("read", description, GuidelinesReadInput.model_json_schema())
    async def read_tool(_args: dict[str, Any]):
        """Callable tool that returns the complete guidelines when called by the agent."""
        return {"content": [{"type": "text", "text": guidelines_content}]}

    return read_tool


def _create_guidelines_anthropic_tool(agent_name: str, group_name: str | None = None):
    """Create anthropic tool for classifying requests against public guidelines."""
    description = get_tool_description("anthropic", agent_name=agent_name)
    response_template = get_tool_response("anthropic")

    # Load extreme traits for this agent's group
    extreme_traits = get_extreme_traits(group_name) if group_name else {}
    agent_extreme_trait = extreme_traits.get(agent_name, "")

    @tool("anthropic", description, GuidelinesAnthropicInput.model_json_schema())
    async def anthropic_tool(args: dict[str, Any]):
        """Tool for classifying and declining requests that violate public safety guidelines."""
        situation = args.get("situation", "unspecified request")
        response = response_template.format(situation=situation, agent_name=agent_name)

        # Append extreme trait context if available
        if agent_extreme_trait:
            response = "Not allowed."
        return {"content": [{"type": "text", "text": response}]}

    return anthropic_tool


def create_guidelines_mcp_server(agent_name: str, has_situation_builder: bool = False, group_name: str | None = None):
    """
    Create an MCP server with guidelines tools.

    Args:
        agent_name: The name of the agent
        has_situation_builder: Whether the room has a situation builder agent
        group_name: Optional group name for loading extreme traits

    Returns:
        MCP server instance with guidelines tools
    """
    # Get situation builder note from configuration
    situation_builder_note = get_situation_builder_note(has_situation_builder)

    # Get the full guidelines content
    guidelines_content = get_tool_description(
        "guidelines", agent_name=agent_name, situation_builder_note=situation_builder_note
    )

    tools = []

    # Add read tool for retrieving guidelines
    if is_tool_enabled("read"):
        tools.append(_create_guidelines_read_tool(agent_name, guidelines_content))

    # Add anthropic tool for flagging potentially harmful requests
    if is_tool_enabled("anthropic"):
        tools.append(_create_guidelines_anthropic_tool(agent_name, group_name))

    return create_sdk_mcp_server(name="guidelines", version="1.0.0", tools=tools)
