"""
Unit tests for utility functions (serializers, helpers, timezone).
"""

from datetime import datetime, timezone

import pytest
from domain.task_identifier import TaskIdentifier
from i18n.serializers import serialize_bool, serialize_utc_datetime
from i18n.timezone import KST, format_kst_timestamp, make_timezone_aware, utc_to_kst


class TestSerializers:
    """Tests for serialization utility functions."""

    @pytest.mark.unit
    def test_serialize_utc_datetime_naive(self):
        """Test serializing naive datetime to timezone-aware."""
        naive_dt = datetime(2024, 1, 15, 12, 0, 0)
        result = serialize_utc_datetime(naive_dt)

        assert result.tzinfo == timezone.utc
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    @pytest.mark.unit
    def test_serialize_utc_datetime_aware(self):
        """Test serializing already timezone-aware datetime."""
        aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = serialize_utc_datetime(aware_dt)

        assert result.tzinfo == timezone.utc
        assert result == aware_dt

    @pytest.mark.unit
    def test_serialize_bool_true(self):
        """Test converting truthy values to boolean."""
        assert serialize_bool(1) is True
        assert serialize_bool(2) is True  # Any non-zero
        assert serialize_bool(100) is True
        assert serialize_bool(True) is True

    @pytest.mark.unit
    def test_serialize_bool_false(self):
        """Test converting falsy values to boolean."""
        assert serialize_bool(0) is False
        assert serialize_bool(False) is False


class TestTaskIdentifier:
    """Tests for TaskIdentifier (used as pool key for room-agent pairs)."""

    @pytest.mark.unit
    def test_task_identifier_creation(self):
        """Test TaskIdentifier creation for room-agent pairs."""
        key = TaskIdentifier(room_id=1, agent_id=2)
        assert isinstance(key, TaskIdentifier)
        assert key.room_id == 1
        assert key.agent_id == 2

        key = TaskIdentifier(room_id=100, agent_id=200)
        assert isinstance(key, TaskIdentifier)
        assert key.room_id == 100
        assert key.agent_id == 200

    @pytest.mark.unit
    def test_task_identifier_uniqueness(self):
        """Test that different room-agent pairs produce different keys."""
        key1 = TaskIdentifier(room_id=1, agent_id=2)
        key2 = TaskIdentifier(room_id=2, agent_id=1)
        key3 = TaskIdentifier(room_id=1, agent_id=1)

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3


class TestTimezone:
    """Tests for timezone utility functions."""

    @pytest.mark.unit
    def test_utc_to_kst(self):
        """Test converting UTC to KST (UTC+9)."""
        utc_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        kst_dt = utc_to_kst(utc_dt)

        assert kst_dt.tzinfo == KST
        assert kst_dt.hour == 21  # 12 + 9 = 21

    @pytest.mark.unit
    def test_utc_to_kst_naive(self):
        """Test converting naive datetime (assumed UTC) to KST."""
        naive_dt = datetime(2024, 1, 15, 12, 0, 0)
        kst_dt = utc_to_kst(naive_dt)

        assert kst_dt.tzinfo == KST
        assert kst_dt.hour == 21  # 12 + 9 = 21

    @pytest.mark.unit
    def test_utc_to_kst_none(self):
        """Test converting None returns None."""
        assert utc_to_kst(None) is None

    @pytest.mark.unit
    def test_make_timezone_aware_naive(self):
        """Test making naive datetime timezone-aware."""
        naive_dt = datetime(2024, 1, 15, 12, 0, 0)
        aware_dt = make_timezone_aware(naive_dt)

        assert aware_dt.tzinfo == timezone.utc

    @pytest.mark.unit
    def test_make_timezone_aware_already_aware(self):
        """Test that already aware datetime is returned as-is."""
        aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=KST)
        result = make_timezone_aware(aware_dt)

        assert result.tzinfo == KST
        assert result == aware_dt

    @pytest.mark.unit
    def test_make_timezone_aware_none(self):
        """Test converting None returns None."""
        assert make_timezone_aware(None) is None

    @pytest.mark.unit
    def test_format_kst_timestamp(self):
        """Test formatting datetime as KST string."""
        utc_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        formatted = format_kst_timestamp(utc_dt)

        assert formatted == "2024-01-15 21:00:00"

    @pytest.mark.unit
    def test_format_kst_timestamp_custom_format(self):
        """Test formatting datetime with custom format string."""
        utc_dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        formatted = format_kst_timestamp(utc_dt, format_str="%Y/%m/%d %H:%M")

        assert formatted == "2024/01/15 21:30"

    @pytest.mark.unit
    def test_format_kst_timestamp_none(self):
        """Test formatting None returns empty string."""
        assert format_kst_timestamp(None) == ""


class TestMemoryParser:
    """Tests for memory parser utility functions."""

    @pytest.mark.unit
    def test_parse_long_term_memory(self, tmp_path):
        """Test parsing long-term memory file with subtitles."""
        from domain.agent_parser import parse_long_term_memory

        # Create test memory file
        memory_file = tmp_path / "long_term_memory.md"
        memory_file.write_text("""## [First Memory]
This is the first memory content.
It can span multiple lines.

## [Second Memory]
This is the second memory.

## [Third Memory]
Third memory here.
""")

        memories = parse_long_term_memory(memory_file)

        assert len(memories) == 3
        assert "First Memory" in memories
        assert "Second Memory" in memories
        assert "Third Memory" in memories
        assert "multiple lines" in memories["First Memory"]

    @pytest.mark.unit
    def test_parse_long_term_memory_not_found(self, tmp_path):
        """Test parsing non-existent memory file."""
        from domain.agent_parser import parse_long_term_memory

        result = parse_long_term_memory(tmp_path / "nonexistent.md")
        assert result == {}

    @pytest.mark.unit
    def test_get_memory_subtitles(self, tmp_path):
        """Test extracting memory subtitles."""
        from domain.agent_parser import get_memory_subtitles

        memory_file = tmp_path / "long_term_memory.md"
        memory_file.write_text("""## [Sub1]
Content 1

## [Sub2]
Content 2
""")

        subtitles = get_memory_subtitles(memory_file)

        assert len(subtitles) == 2
        assert "Sub1" in subtitles
        assert "Sub2" in subtitles

    @pytest.mark.unit
    def test_get_memory_by_subtitle(self, tmp_path):
        """Test retrieving specific memory by subtitle."""
        from domain.agent_parser import get_memory_by_subtitle

        memory_file = tmp_path / "long_term_memory.md"
        memory_file.write_text("""## [Important]
This is important information.

## [Random]
Random stuff here.
""")

        memory = get_memory_by_subtitle(memory_file, "Important")

        assert memory is not None
        assert "important information" in memory

    @pytest.mark.unit
    def test_get_memory_by_subtitle_not_found(self, tmp_path):
        """Test retrieving non-existent memory."""
        from domain.agent_parser import get_memory_by_subtitle

        memory_file = tmp_path / "long_term_memory.md"
        memory_file.write_text("## [Exists]\nContent")

        memory = get_memory_by_subtitle(memory_file, "DoesNotExist")

        assert memory is None
