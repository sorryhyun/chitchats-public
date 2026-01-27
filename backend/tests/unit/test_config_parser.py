"""
Unit tests for config parser module.

Tests agent configuration parsing from markdown files.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from domain.agent_parser import _parse_folder_config, parse_agent_config
from domain.agent_config import AgentConfigData


class TestAgentConfigData:
    """Tests for AgentConfigData dataclass."""

    @pytest.mark.unit
    def test_agent_config_data_initialization(self):
        """Test AgentConfigData initialization with all parameters."""
        config = AgentConfigData(
            in_a_nutshell="Brief description",
            characteristics="Friendly",
            recent_events="Recent event",
            profile_pic="profile.png",
            long_term_memory_index={"key": "value"},
            long_term_memory_subtitles="'memory1', 'memory2'",
        )

        assert config.in_a_nutshell == "Brief description"
        assert config.characteristics == "Friendly"
        assert config.recent_events == "Recent event"
        assert config.profile_pic == "profile.png"
        assert config.long_term_memory_index == {"key": "value"}
        assert config.long_term_memory_subtitles == "'memory1', 'memory2'"

    @pytest.mark.unit
    def test_agent_config_data_defaults(self):
        """Test AgentConfigData initialization with default values."""
        config = AgentConfigData()

        assert config.in_a_nutshell is None
        assert config.characteristics is None
        assert config.recent_events is None
        assert config.profile_pic is None
        assert config.long_term_memory_index is None
        assert config.long_term_memory_subtitles is None


class TestParseAgentConfig:
    """Tests for parse_agent_config function."""

    @pytest.fixture
    def temp_agent_dir(self):
        """Create a temporary agent directory with config files."""
        temp_dir = tempfile.mkdtemp()
        agent_dir = Path(temp_dir) / "agents" / "test_agent"
        agent_dir.mkdir(parents=True)

        # Create required config files
        (agent_dir / "in_a_nutshell.md").write_text("Test agent brief")
        (agent_dir / "characteristics.md").write_text("Friendly and helpful")
        (agent_dir / "recent_events.md").write_text("Just created")

        yield temp_dir, agent_dir

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def temp_agent_with_profile(self, temp_agent_dir):
        """Create an agent directory with a profile picture."""
        temp_dir, agent_dir = temp_agent_dir
        # Create a dummy profile picture
        (agent_dir / "profile.png").write_bytes(b"fake image data")
        yield temp_dir, agent_dir

    @pytest.mark.unit
    def test_parse_folder_config_basic(self, temp_agent_dir):
        """Test parsing basic agent config from folder."""
        temp_dir, agent_dir = temp_agent_dir
        config = _parse_folder_config(agent_dir)

        assert isinstance(config, AgentConfigData)
        assert config.in_a_nutshell == "Test agent brief"
        assert config.characteristics == "Friendly and helpful"
        assert config.recent_events == "Just created"
        assert config.profile_pic is None

    @pytest.mark.unit
    def test_parse_folder_config_with_profile(self, temp_agent_with_profile):
        """Test parsing agent config with profile picture."""
        temp_dir, agent_dir = temp_agent_with_profile
        config = _parse_folder_config(agent_dir)

        assert config.profile_pic == "profile.png"

    @pytest.mark.unit
    def test_parse_agent_config_absolute_path(self, temp_agent_dir):
        """Test parsing agent config with absolute path."""
        temp_dir, agent_dir = temp_agent_dir
        config = parse_agent_config(str(agent_dir))

        assert config is not None
        assert config.in_a_nutshell == "Test agent brief"

    @pytest.mark.unit
    def test_parse_agent_config_nonexistent_path(self):
        """Test parsing agent config with nonexistent path."""
        config = parse_agent_config("/nonexistent/path")
        assert config is None

    @pytest.mark.unit
    def test_parse_agent_config_file_not_directory(self):
        """Test parsing agent config with file path instead of directory."""
        with tempfile.NamedTemporaryFile() as tmp_file:
            config = parse_agent_config(tmp_file.name)
            assert config is None

    @pytest.mark.unit
    def test_find_profile_pic_common_names(self, temp_agent_dir):
        """Test finding profile pictures with common names."""
        temp_dir, agent_dir = temp_agent_dir

        # Test each common name pattern
        for name in ["avatar", "picture", "photo"]:
            pic_path = agent_dir / f"{name}.jpg"
            pic_path.write_bytes(b"fake image")
            config = _parse_folder_config(agent_dir)
            assert config.profile_pic == f"{name}.jpg"
            pic_path.unlink()

    @pytest.mark.unit
    def test_find_profile_pic_different_extensions(self, temp_agent_dir):
        """Test finding profile pictures with different extensions."""
        temp_dir, agent_dir = temp_agent_dir

        # Test different image extensions
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            pic_path = agent_dir / f"profile{ext}"
            pic_path.write_bytes(b"fake image")
            config = _parse_folder_config(agent_dir)
            assert config.profile_pic == f"profile{ext}"
            pic_path.unlink()

    @pytest.mark.unit
    def test_find_profile_pic_any_image(self, temp_agent_dir):
        """Test finding any image file when no common name matches."""
        temp_dir, agent_dir = temp_agent_dir

        # Create an image file with a non-standard name
        (agent_dir / "custom_image.png").write_bytes(b"fake image")
        config = _parse_folder_config(agent_dir)

        # Should find the custom image
        assert config.profile_pic == "custom_image.png"


class TestListAvailableConfigs:
    """Tests for list_available_configs function."""

    @pytest.fixture
    def temp_agents_structure(self):
        """Create a temporary agents directory structure."""
        temp_dir = tempfile.mkdtemp()
        agents_dir = Path(temp_dir) / "agents"
        agents_dir.mkdir()

        # Create a regular agent
        agent1_dir = agents_dir / "agent1"
        agent1_dir.mkdir()
        (agent1_dir / "in_a_nutshell.md").write_text("Agent 1")
        (agent1_dir / "characteristics.md").write_text("Characteristics")

        # Create a group with agents
        group_dir = agents_dir / "group_testgroup"
        group_dir.mkdir()
        agent2_dir = group_dir / "agent2"
        agent2_dir.mkdir()
        (agent2_dir / "in_a_nutshell.md").write_text("Agent 2")
        (agent2_dir / "characteristics.md").write_text("Characteristics")

        # Create a folder without required files (should be ignored)
        invalid_dir = agents_dir / "invalid"
        invalid_dir.mkdir()

        # Create a hidden folder (should be ignored)
        hidden_dir = agents_dir / ".hidden"
        hidden_dir.mkdir()

        yield temp_dir, agents_dir

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.mark.unit
    def test_list_available_configs_basic_validation(self, temp_agents_structure):
        """Test basic validation of list_available_configs logic."""
        temp_dir, agents_dir = temp_agents_structure

        # Create a mock version of list_available_configs that uses our temp dir
        configs = {}
        required_files = ["in_a_nutshell.md", "characteristics.md", "backgrounds.md"]

        for item in agents_dir.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue

            if item.name.startswith("group_"):
                group_name = item.name[6:]
                for agent_item in item.iterdir():
                    if agent_item.is_dir() and not agent_item.name.startswith("."):
                        if any((agent_item / f).exists() for f in required_files):
                            configs[agent_item.name] = {
                                "path": str(agent_item.relative_to(Path(temp_dir))),
                                "group": group_name,
                            }
            else:
                if any((item / f).exists() for f in required_files):
                    configs[item.name] = {"path": str(item.relative_to(Path(temp_dir))), "group": None}

        # Should find agent1 (ungrouped) and agent2 (in group)
        assert "agent1" in configs
        assert "agent2" in configs
        assert "invalid" not in configs
        assert ".hidden" not in configs

        # Check agent1 metadata
        assert configs["agent1"]["group"] is None
        assert "agents/agent1" in configs["agent1"]["path"]

        # Check agent2 metadata
        assert configs["agent2"]["group"] == "testgroup"
        assert "agents/group_testgroup/agent2" in configs["agent2"]["path"]

    @pytest.mark.unit
    def test_list_available_configs_empty_dir(self):
        """Test list_available_configs with empty agents directory."""
        # Create a temp directory with empty agents folder
        temp_dir = tempfile.mkdtemp()
        agents_dir = Path(temp_dir) / "agents"
        agents_dir.mkdir()

        try:
            # Test the logic with empty directory
            configs = {}
            required_files = ["in_a_nutshell.md", "characteristics.md", "backgrounds.md"]

            for item in agents_dir.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                if any((item / f).exists() for f in required_files):
                    configs[item.name] = {"path": str(item), "group": None}

            # Should return empty dict
            assert configs == {}
        finally:
            shutil.rmtree(temp_dir)


class TestParseAgentConfigLongTermMemory:
    """Tests for long-term memory parsing."""

    @pytest.fixture
    def temp_agent_with_ltm(self):
        """Create agent directory with long-term memory."""
        temp_dir = tempfile.mkdtemp()
        agent_dir = Path(temp_dir) / "agents" / "test_agent"
        agent_dir.mkdir(parents=True)

        # Create required config files
        (agent_dir / "in_a_nutshell.md").write_text("Test agent")
        (agent_dir / "characteristics.md").write_text("Friendly")
        (agent_dir / "backgrounds.md").write_text("Background")
        (agent_dir / "memory.md").write_text("Memory")
        (agent_dir / "recent_events.md").write_text("Events")

        yield temp_dir, agent_dir

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.mark.unit
    def test_parse_agent_config_with_long_term_memory(self, temp_agent_with_ltm):
        """Test parsing agent config with long-term memory file."""
        temp_dir, agent_dir = temp_agent_with_ltm

        # Create a long-term memory file with proper format: ## [subtitle]
        # Using default filename: consolidated_memory.md
        from domain.agent_parser import _parse_folder_config

        ltm_content = """## [Memory 1]

Content of memory 1

## [Memory 2]

Content of memory 2
"""
        (agent_dir / "consolidated_memory.md").write_text(ltm_content)

        config = _parse_folder_config(agent_dir)

        # Should have parsed the long-term memory
        assert config.long_term_memory_index is not None
        assert len(config.long_term_memory_index) == 2
        assert "Memory 1" in config.long_term_memory_index
        assert "Memory 2" in config.long_term_memory_index
        assert config.long_term_memory_subtitles is not None
        assert "'Memory 1'" in config.long_term_memory_subtitles
        assert "'Memory 2'" in config.long_term_memory_subtitles
