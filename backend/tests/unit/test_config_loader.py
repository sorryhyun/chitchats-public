"""
Unit tests for config loader module.

Tests YAML configuration loading, caching, and hot-reloading.
"""

import tempfile
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from config import (
    _config_cache,
    _get_file_mtime,
    _load_yaml_file,
    get_cached_config,
    get_debug_config,
    get_tool_description,
)
from core.settings import Settings, reset_settings

# Alias for backward compatibility in tests
_get_cached_config = get_cached_config


class TestFileMtime:
    """Tests for _get_file_mtime function."""

    @pytest.mark.unit
    def test_get_file_mtime_existing_file(self):
        """Test getting modification time of existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                mtime = _get_file_mtime(tmp_path)
                assert mtime > 0
                assert isinstance(mtime, float)
            finally:
                tmp_path.unlink()

    @pytest.mark.unit
    def test_get_file_mtime_nonexistent_file(self):
        """Test getting modification time of nonexistent file returns 0."""
        mtime = _get_file_mtime(Path("/nonexistent/file.yaml"))
        assert mtime == 0.0


class TestLoadYamlFile:
    """Tests for _load_yaml_file function."""

    @pytest.mark.unit
    def test_load_yaml_file_valid(self):
        """Test loading valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("key: value\nnumber: 42\n")
            tmp_path = Path(tmp.name)

        try:
            result = _load_yaml_file(tmp_path)
            assert result == {"key": "value", "number": 42}
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_load_yaml_file_empty(self):
        """Test loading empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("")
            tmp_path = Path(tmp.name)

        try:
            result = _load_yaml_file(tmp_path)
            assert result == {}
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_load_yaml_file_nonexistent(self):
        """Test loading nonexistent YAML file returns empty dict."""
        result = _load_yaml_file(Path("/nonexistent/file.yaml"))
        assert result == {}

    @pytest.mark.unit
    def test_load_yaml_file_nested_structure(self):
        """Test loading YAML file with nested structure."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("parent:\n  child1: value1\n  child2: value2\n")
            tmp_path = Path(tmp.name)

        try:
            result = _load_yaml_file(tmp_path)
            assert result == {"parent": {"child1": "value1", "child2": "value2"}}
        finally:
            tmp_path.unlink()


class TestCachedConfig:
    """Tests for _get_cached_config function."""

    def setup_method(self):
        """Clear cache before each test."""
        _config_cache.clear()

    @pytest.mark.unit
    def test_get_cached_config_first_load(self):
        """Test loading config for the first time (cache miss)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("test: value\n")
            tmp_path = Path(tmp.name)

        try:
            result = _get_cached_config(tmp_path)
            assert result == {"test": "value"}
            assert str(tmp_path) in _config_cache
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_get_cached_config_cache_hit(self):
        """Test loading config from cache (cache hit)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("test: value\n")
            tmp_path = Path(tmp.name)

        try:
            # First load
            result1 = _get_cached_config(tmp_path)
            # Second load (should hit cache)
            result2 = _get_cached_config(tmp_path)

            assert result1 == result2
            assert result2 == {"test": "value"}
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_get_cached_config_force_reload(self):
        """Test force reloading config bypasses cache."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("test: value1\n")
            tmp_path = Path(tmp.name)

        try:
            # First load
            result1 = _get_cached_config(tmp_path)
            assert result1 == {"test": "value1"}

            # Modify file
            with open(tmp_path, "w") as f:
                f.write("test: value2\n")

            # Force reload
            result2 = _get_cached_config(tmp_path, force_reload=True)
            assert result2 == {"test": "value2"}
        finally:
            tmp_path.unlink()


class TestGetDebugConfig:
    """Tests for get_debug_config function."""

    def setup_method(self):
        """Clear cache before each test."""
        _config_cache.clear()
        reset_settings()

    def teardown_method(self):
        """Reset settings after each test."""
        reset_settings()

    @pytest.mark.unit
    def test_get_debug_config_env_override_true(self, monkeypatch):
        """Test DEBUG_AGENTS environment variable overrides config."""
        # Create a temporary debug config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("debug:\n  enabled: false\n")
            tmp_path = Path(tmp.name)

        try:
            # Set environment variable
            monkeypatch.setenv("DEBUG_AGENTS", "true")

            # Patch the settings property
            with patch.object(Settings, "debug_config_path", new_callable=PropertyMock, return_value=tmp_path):
                config = get_debug_config()
                assert config["debug"]["enabled"] is True
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_get_debug_config_env_override_false(self, monkeypatch):
        """Test DEBUG_AGENTS=false overrides config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("debug:\n  enabled: true\n")
            tmp_path = Path(tmp.name)

        try:
            monkeypatch.setenv("DEBUG_AGENTS", "false")

            with patch.object(Settings, "debug_config_path", new_callable=PropertyMock, return_value=tmp_path):
                config = get_debug_config()
                assert config["debug"]["enabled"] is False
        finally:
            tmp_path.unlink()

    @pytest.mark.unit
    def test_get_debug_config_no_env_override(self, monkeypatch):
        """Test config is used when no environment variable is set."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write("debug:\n  enabled: true\n")
            tmp_path = Path(tmp.name)

        try:
            # Make sure env var is not set
            monkeypatch.delenv("DEBUG_AGENTS", raising=False)

            with patch.object(Settings, "debug_config_path", new_callable=PropertyMock, return_value=tmp_path):
                config = get_debug_config()
                assert config["debug"]["enabled"] is True
        finally:
            tmp_path.unlink()


class TestGetToolDescription:
    """Tests for get_tool_description function."""

    def setup_method(self):
        """Clear cache before each test."""
        _config_cache.clear()
        reset_settings()

    def teardown_method(self):
        """Reset settings after each test."""
        reset_settings()

    @pytest.mark.unit
    def test_get_tool_description_basic(self):
        """Test getting basic tool description from Python registry."""
        # Test with real tool from registry (skip tool has {agent_name} placeholder)
        desc = get_tool_description("skip", agent_name="Alice")
        assert desc is not None
        assert "Alice" in desc
        assert "skip" in desc.lower()

    @pytest.mark.unit
    def test_get_tool_description_disabled_tool(self):
        """Test getting description of disabled tool returns None."""
        # 'read' tool is disabled by default in the registry
        desc = get_tool_description("read")
        assert desc is None

    @pytest.mark.unit
    def test_get_tool_description_not_found(self):
        """Test getting description of nonexistent tool returns None."""
        desc = get_tool_description("nonexistent_tool")
        assert desc is None

    @pytest.mark.unit
    def test_get_tool_description_with_variables(self):
        """Test tool description with template variables."""
        # Test recall tool which has {agent_name} and {memory_subtitles} placeholders
        desc = get_tool_description(
            "recall",
            agent_name="Alice",
            memory_subtitles="memory1, memory2",
        )
        assert desc is not None
        assert "Alice" in desc
        assert "memory1, memory2" in desc

    @pytest.mark.unit
    def test_get_tool_description_read_tool(self):
        """Test getting 'read' (guidelines) tool description.

        Note: The 'guidelines' tool was renamed to 'read' and is now in the
        mcp__guidelines__read namespace. It's disabled by default.
        """
        # The 'read' tool exists in TOOLS but is disabled by default
        # When enabled, it should return a description with agent_name substituted
        desc = get_tool_description("read", agent_name="Alice")
        # 'read' tool is disabled by default, so it should return None
        assert desc is None

        # Test that when looking up 'anthropic' tool (which is enabled for claude)
        desc = get_tool_description("anthropic", agent_name="Alice", provider="claude")
        assert desc is not None
        assert "real-world harm" in desc.lower() or "Anthropic" in desc
