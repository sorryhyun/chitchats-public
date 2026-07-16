"""
Unit tests for the image MCP server.

Covers appearance extraction from characteristics.md, prompt building for the
draw tool, and recovery of the image URL from a tool result.
"""

from unittest.mock import patch

import pytest
from domain.agent_parser import extract_appearance, get_appearance_by_folder
from infrastructure.generated_images import URL_PREFIX, extract_image_urls
from mcp_servers.image_server import _build_prompt, _handle_draw, _resolve_cast

CHARACTERISTICS = """## 외형
- **검은 생머리**: 어깨까지 내려오며 앞머리가 이마를 덮음
- **작은 체구**: 약 156cm

## 성격
- **중2병 대사**: "폭렬하라!"를 즐겨 외침
"""

CONTEXT = {
    "agent_name": "릿카",
    "agent_group": None,
    "config_file": None,
    "provider": "codex",
}


class TestExtractAppearance:
    """Tests for pulling the appearance section out of characteristics.md."""

    @pytest.mark.unit
    def test_extracts_korean_section_without_personality(self):
        appearance = extract_appearance(CHARACTERISTICS)

        assert "검은 생머리" in appearance
        assert "156cm" in appearance
        # The 성격 section must not bleed into the appearance
        assert "폭렬하라" not in appearance
        assert "## 성격" not in appearance

    @pytest.mark.unit
    def test_extracts_english_section(self):
        appearance = extract_appearance("## Appearance\n- **Glasses**: Black-rimmed\n\n## Personality\n- Analytical")

        assert appearance == "- **Glasses**: Black-rimmed"

    @pytest.mark.unit
    def test_appearance_as_last_section(self):
        assert extract_appearance("## 성격\n- Kind\n\n## 외형\n- **Tall**: 190cm") == "- **Tall**: 190cm"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        ["", "## 성격\n- Kind only, no appearance", "no headers at all"],
    )
    def test_returns_empty_when_section_missing(self, text):
        assert extract_appearance(text) == ""

    @pytest.mark.unit
    def test_reads_from_agent_folder(self, tmp_path):
        (tmp_path / "characteristics.md").write_text(CHARACTERISTICS, encoding="utf-8")

        assert "검은 생머리" in get_appearance_by_folder(tmp_path)

    @pytest.mark.unit
    def test_missing_characteristics_file_is_not_an_error(self, tmp_path):
        assert get_appearance_by_folder(tmp_path) == ""


class TestResolveCast:
    """Tests for deciding who is in the picture."""

    @pytest.mark.unit
    def test_no_characters_means_the_drawing_agent(self):
        assert _resolve_cast(None, "릿카") == ["릿카"]
        assert _resolve_cast([], "릿카") == ["릿카"]

    @pytest.mark.unit
    def test_named_characters_are_the_cast(self):
        assert _resolve_cast(["프리렌", "펠른"], "릿카") == ["프리렌", "펠른"]

    @pytest.mark.unit
    def test_blank_names_fall_back_to_the_agent(self):
        assert _resolve_cast(["  "], "릿카") == ["릿카"]


class TestBuildPrompt:
    """Tests for weaving appearance into the scene description."""

    @pytest.mark.unit
    def test_appearance_is_prepended_to_the_scene(self):
        with patch("domain.agent_parser.get_appearance_by_name", return_value="- **검은 생머리**: 어깨까지"):
            prompt = _build_prompt("selfie in the classroom", ["릿카"], CONTEXT)

        assert "릿카 looks like this:" in prompt
        assert "검은 생머리" in prompt
        assert "Scene to draw:\nselfie in the classroom" in prompt

    @pytest.mark.unit
    def test_each_character_gets_a_block(self):
        with patch("domain.agent_parser.get_appearance_by_name", side_effect=lambda n: f"- looks like {n}"):
            prompt = _build_prompt("at the beach", ["프리렌", "펠른"], CONTEXT)

        assert "프리렌 looks like this:" in prompt
        assert "펠른 looks like this:" in prompt

    @pytest.mark.unit
    def test_scene_passes_through_when_no_appearance_on_file(self):
        with patch("domain.agent_parser.get_appearance_by_name", return_value=""):
            assert _build_prompt("a sunset", ["나레이터"], CONTEXT) == "a sunset"


class TestExtractImageUrls:
    """Tests for recovering image URLs from tool result text."""

    @pytest.mark.unit
    def test_finds_url_in_response_text(self):
        text = f"The picture is now posted in the chat: {URL_PREFIX}/abc123def.png\nThe others can see it."

        assert extract_image_urls(text) == [f"{URL_PREFIX}/abc123def.png"]

    @pytest.mark.unit
    def test_deduplicates_and_keeps_order(self):
        text = f"{URL_PREFIX}/aaa.png and {URL_PREFIX}/bbb.webp and {URL_PREFIX}/aaa.png"

        assert extract_image_urls(text) == [f"{URL_PREFIX}/aaa.png", f"{URL_PREFIX}/bbb.webp"]

    @pytest.mark.unit
    @pytest.mark.parametrize("text", ["", "no image here", "/other_images/abc.png"])
    def test_returns_empty_when_no_url(self, text):
        assert extract_image_urls(text) == []


class TestHandleDraw:
    """Tests for the draw tool handler."""

    @pytest.mark.unit
    def test_empty_prompt_is_rejected_without_calling_the_endpoint(self):
        with patch("mcp_servers.image_server._generate_image") as generate:
            result = _handle_draw("draw", {"prompt": "   "}, CONTEXT)

        assert "cannot be empty" in result[0].text
        generate.assert_not_called()

    @pytest.mark.unit
    def test_successful_draw_returns_the_url(self):
        with (
            patch("mcp_servers.image_server._generate_image", return_value="Yg==") as generate,
            patch(
                "infrastructure.generated_images.save_generated_image",
                return_value=(f"{URL_PREFIX}/abc.png", "image/png"),
            ),
            patch("domain.agent_parser.get_appearance_by_name", return_value="- **검은 생머리**: 어깨까지"),
        ):
            result = _handle_draw("draw", {"prompt": "selfie"}, CONTEXT)

        assert f"{URL_PREFIX}/abc.png" in result[0].text
        # Appearance was woven in rather than the raw prompt being sent through
        assert "검은 생머리" in generate.call_args[0][0]

    @pytest.mark.unit
    def test_involve_appearance_false_sends_the_raw_prompt(self):
        with (
            patch("mcp_servers.image_server._generate_image", return_value="Yg==") as generate,
            patch(
                "infrastructure.generated_images.save_generated_image",
                return_value=(f"{URL_PREFIX}/abc.png", "image/png"),
            ),
        ):
            _handle_draw("draw", {"prompt": "an empty street", "involve_appearance": False}, CONTEXT)

        assert generate.call_args[0][0] == "an empty street"

    @pytest.mark.unit
    def test_generation_failure_is_reported_in_character_terms(self):
        with patch("mcp_servers.image_server._generate_image", side_effect=RuntimeError("HTTP 401")):
            result = _handle_draw("draw", {"prompt": "selfie", "involve_appearance": False}, CONTEXT)

        assert "could not be created" in result[0].text
        assert "HTTP 401" in result[0].text

    @pytest.mark.unit
    def test_save_failure_is_reported(self):
        with (
            patch("mcp_servers.image_server._generate_image", return_value="Yg=="),
            patch("infrastructure.generated_images.save_generated_image", return_value=None),
        ):
            result = _handle_draw("draw", {"prompt": "selfie", "involve_appearance": False}, CONTEXT)

        assert "could not be saved" in result[0].text
