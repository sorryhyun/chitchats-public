"""Tools API routes for exposing available tools to the frontend."""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Query
from mcp_servers.config.tools import TOOLS, is_tool_enabled
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("ToolsRouter")


class ToolResponse(BaseModel):
    """Response model for a tool."""

    name: str
    group: str
    description: str
    input_schema: dict


@router.get("/tools", response_model=list[ToolResponse])
async def list_tools(
    provider: Optional[str] = Query(None, description="Filter tools by provider (claude, codex, custom)"),
):
    """
    List available tools for agent invocation.

    Returns tools from the TOOLS registry that are enabled and available
    for the specified provider. Each tool includes its JSON schema for
    frontend form generation.
    """
    tools = []

    for tool_name, tool_def in TOOLS.items():
        # Check if tool is enabled and available for the provider
        if not is_tool_enabled(tool_name, provider=provider):
            continue

        # Get JSON schema from the Pydantic input model
        input_schema = tool_def.input_model.model_json_schema()

        # Remove schema metadata fields that aren't needed for form generation
        input_schema.pop("title", None)
        input_schema.pop("$defs", None)

        # Create a clean description without template variables
        description = tool_def.description
        # Remove template variables like {agent_name}, {memory_subtitles}
        description = re.sub(r"\{[^}]+\}", "", description).strip()
        # Clean up any double spaces
        description = re.sub(r"\s+", " ", description)

        tools.append(
            ToolResponse(
                name=tool_name,
                group=tool_def.group,
                description=description,
                input_schema=input_schema,
            )
        )

    return tools
