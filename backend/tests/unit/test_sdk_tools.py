"""
Unit tests for SDK tools.

Tests tool creation, configuration, and execution.
"""

from unittest.mock import Mock, patch

import pytest
from sdk.brain_tools import create_character_config_mcp_server, create_character_config_tool
from sdk.guidelines_tools import create_guidelines_mcp_server
from sdk.tools import create_action_mcp_server, create_action_tools


class TestCreateActionTools:
    """Tests for create_action_tools function."""

    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    def test_create_skip_tool(self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled):
        """Test creating skip tool."""
        mock_is_enabled.return_value = True
        mock_get_description.return_value = "Skip tool description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Tool executed"

        tools = create_action_tools("TestAgent")

        # Should create at least skip tool
        assert len(tools) > 0

        # Verify tool was configured correctly
        mock_get_description.assert_called()
        mock_get_schema.assert_called()

    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    def test_create_memorize_tool(self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled):
        """Test creating memorize tool."""
        mock_is_enabled.return_value = True
        mock_get_description.return_value = "Memorize tool description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Memory recorded"

        tools = create_action_tools("TestAgent")

        # Should include memorize tool
        assert len(tools) >= 2  # At least skip and memorize

    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    def test_create_recall_tool_with_memory_index(
        self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled
    ):
        """Test creating recall tool when long-term memory is available."""

        def is_enabled_side_effect(tool_name):
            return tool_name in ["skip", "memorize", "recall"]

        mock_is_enabled.side_effect = is_enabled_side_effect
        mock_get_description.return_value = "Tool description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Tool executed"

        memory_index = {"childhood": "Memory about childhood", "training": "Memory about training"}

        tools = create_action_tools("TestAgent", long_term_memory_index=memory_index)

        # Should include recall tool
        assert len(tools) == 3  # skip, memorize, recall

    @patch("sdk.action_tools.is_tool_enabled")
    def test_create_tools_when_disabled(self, mock_is_enabled):
        """Test that disabled tools are not created."""
        mock_is_enabled.return_value = False

        tools = create_action_tools("TestAgent")

        # No tools should be created
        assert len(tools) == 0

    @pytest.mark.asyncio
    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    async def test_skip_tool_execution(self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled):
        """Test executing the skip tool."""
        mock_is_enabled.side_effect = lambda x: x == "skip"
        mock_get_description.return_value = "Skip description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Skipped successfully"

        tools = create_action_tools("TestAgent")

        # Verify skip tool was created
        assert len(tools) == 1
        assert tools[0].name == "skip"
        assert "Skip description" in tools[0].description

    @pytest.mark.asyncio
    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    async def test_memorize_tool_execution(
        self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled
    ):
        """Test creating the memorize tool."""
        mock_is_enabled.side_effect = lambda x: x == "memorize"
        mock_get_description.return_value = "Memorize description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Memory recorded: Important event"

        tools = create_action_tools("TestAgent")

        # Verify memorize tool was created
        assert len(tools) == 1
        assert tools[0].name == "memorize"
        assert "Memorize description" in tools[0].description

    @pytest.mark.asyncio
    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    @patch("sdk.action_tools.get_tool_response")
    async def test_recall_tool_creation_success(
        self, mock_get_response, mock_get_schema, mock_get_description, mock_is_enabled
    ):
        """Test creating recall tool when memory index is provided."""
        mock_is_enabled.side_effect = lambda x: x == "recall"
        mock_get_description.return_value = "Recall description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_response.return_value = "Memory: Childhood memories..."

        memory_index = {"childhood": "Childhood memories..."}
        tools = create_action_tools("TestAgent", long_term_memory_index=memory_index)

        # Verify recall tool was created
        assert len(tools) == 1
        assert tools[0].name == "recall"
        assert "Recall description" in tools[0].description

    @pytest.mark.asyncio
    @patch("sdk.action_tools.is_tool_enabled")
    @patch("sdk.action_tools.get_tool_description")
    @patch("sdk.action_tools.get_tool_input_schema")
    async def test_recall_tool_without_memory_index(self, mock_get_schema, mock_get_description, mock_is_enabled):
        """Test that recall tool is not created when memory index is not provided."""
        mock_is_enabled.side_effect = lambda x: x == "recall"
        mock_get_description.return_value = "Recall description"
        mock_get_schema.return_value = {"type": "object"}

        # No memory index provided
        tools = create_action_tools("TestAgent", long_term_memory_index=None)

        # Recall tool should not be created without memory index
        assert len(tools) == 0


class TestCreateGuidelinesMCPServer:
    """Tests for create_guidelines_mcp_server function."""

    @patch("sdk.guidelines_tools.is_tool_enabled")
    @patch("sdk.guidelines_tools.get_tool_description")
    @patch("sdk.guidelines_tools.get_tool_input_schema")
    @patch("sdk.guidelines_tools.get_situation_builder_note")
    @patch("sdk.guidelines_tools.create_sdk_mcp_server")
    def test_create_guidelines_mcp_server_description_mode(
        self, mock_create_mcp, mock_get_note, mock_get_schema, mock_get_description, mock_is_enabled
    ):
        """Test creating guidelines MCP server in description mode."""
        mock_is_enabled.return_value = True
        mock_get_description.return_value = "Guidelines content"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_note.return_value = ""
        mock_create_mcp.return_value = Mock()

        with patch("sdk.guidelines_tools.GUIDELINE_READ_MODE", "description"):
            server = create_guidelines_mcp_server(agent_name="TestAgent", has_situation_builder=False)

        # Should create MCP server
        assert server is not None
        mock_create_mcp.assert_called_once()

    @patch("sdk.guidelines_tools.is_tool_enabled")
    @patch("sdk.guidelines_tools.get_tool_description")
    @patch("sdk.guidelines_tools.get_tool_input_schema")
    @patch("sdk.guidelines_tools.get_situation_builder_note")
    @patch("sdk.guidelines_tools.create_sdk_mcp_server")
    def test_create_guidelines_mcp_server_active_mode(
        self, mock_create_mcp, mock_get_note, mock_get_schema, mock_get_description, mock_is_enabled
    ):
        """Test creating guidelines MCP server in active tool mode."""
        mock_is_enabled.return_value = True
        mock_get_description.return_value = "Read tool description"
        mock_get_schema.return_value = {"type": "object"}
        mock_get_note.return_value = ""
        mock_create_mcp.return_value = Mock()

        with patch("sdk.guidelines_tools.GUIDELINE_READ_MODE", "active_tool"):
            server = create_guidelines_mcp_server(agent_name="TestAgent", has_situation_builder=True)

        # Should create MCP server with read tool
        assert server is not None
        mock_create_mcp.assert_called_once()


class TestCreateCharacterConfigTools:
    """Tests for create_character_config_tool function."""

    def test_create_character_config_tool_with_all_sections(self):
        """Test creating character config tool with all config sections."""
        tools = create_character_config_tool(
            agent_name="TestAgent",
            in_a_nutshell="Brief identity",
            characteristics="Personality traits",
        )

        # Should create character identity tool
        assert len(tools) == 1
        assert tools[0].name == "character_identity"
        assert "TestAgent" in tools[0].description
        assert "Brief identity" in tools[0].description
        assert "Personality traits" in tools[0].description

    def test_create_character_config_tool_with_no_sections(self):
        """Test that no tools are created when no sections provided."""
        tools = create_character_config_tool(agent_name="TestAgent")

        # No tools should be created
        assert len(tools) == 0

    def test_create_character_config_tool_with_partial_sections(self):
        """Test creating character config tool with only some sections."""
        tools = create_character_config_tool(
            agent_name="TestAgent",
            in_a_nutshell="Brief identity",
            # No characteristics
        )

        # Should create tool with only in_a_nutshell
        assert len(tools) == 1


class TestCreateActionMCPServer:
    """Tests for create_action_mcp_server function."""

    @patch("sdk.action_tools.create_sdk_mcp_server")
    @patch("sdk.action_tools.create_action_tools")
    def test_create_action_mcp_server_basic(self, mock_create_tools, mock_create_mcp_server):
        """Test creating action MCP server."""
        mock_tools = [Mock(), Mock()]
        mock_create_tools.return_value = mock_tools
        mock_create_mcp_server.return_value = Mock()

        server = create_action_mcp_server("TestAgent")

        # Should call create_action_tools
        mock_create_tools.assert_called_once_with("TestAgent", None, None, None)

        # Should create MCP server with tools
        mock_create_mcp_server.assert_called_once_with(name="action", version="1.0.0", tools=mock_tools)

    @patch("sdk.action_tools.create_sdk_mcp_server")
    @patch("sdk.action_tools.create_action_tools")
    def test_create_action_mcp_server_with_memory_index(self, mock_create_tools, mock_create_mcp_server):
        """Test creating action MCP server with memory index."""
        mock_tools = [Mock(), Mock(), Mock()]
        mock_create_tools.return_value = mock_tools
        mock_create_mcp_server.return_value = Mock()

        memory_index = {"key": "value"}
        server = create_action_mcp_server("TestAgent", long_term_memory_index=memory_index)

        # Should pass memory index to create_action_tools
        mock_create_tools.assert_called_once_with("TestAgent", None, None, memory_index)


class TestCreateCharacterConfigMCPServer:
    """Tests for create_character_config_mcp_server function."""

    @patch("sdk.brain_tools.create_sdk_mcp_server")
    @patch("sdk.brain_tools.create_character_config_tool")
    def test_create_character_config_mcp_server_basic(self, mock_create_tools, mock_create_mcp_server):
        """Test creating character config MCP server."""
        mock_tools = [Mock()]
        mock_create_tools.return_value = mock_tools
        mock_create_mcp_server.return_value = Mock()

        server = create_character_config_mcp_server(agent_name="TestAgent", in_a_nutshell="Brief description")

        # Should call create_character_config_tool with parameters
        mock_create_tools.assert_called_once_with(
            agent_name="TestAgent", in_a_nutshell="Brief description", characteristics=None
        )

        # Should create MCP server
        mock_create_mcp_server.assert_called_once_with(name="character", version="1.0.0", tools=mock_tools)

    @patch("sdk.brain_tools.create_sdk_mcp_server")
    @patch("sdk.brain_tools.create_character_config_tool")
    def test_create_character_config_mcp_server_with_all_params(self, mock_create_tools, mock_create_mcp_server):
        """Test creating character config MCP server with all parameters."""
        mock_tools = [Mock(), Mock()]
        mock_create_tools.return_value = mock_tools
        mock_create_mcp_server.return_value = Mock()

        server = create_character_config_mcp_server(
            agent_name="TestAgent",
            in_a_nutshell="Brief",
            characteristics="Traits",
        )

        # Should pass all parameters
        mock_create_tools.assert_called_once_with(
            agent_name="TestAgent", in_a_nutshell="Brief", characteristics="Traits"
        )
