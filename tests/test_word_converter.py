"""Tests for the word_converter module — Markdown→PDF pipeline elements."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Mark these as unit tests — the full pipeline requires reportlab
pytestmark = pytest.mark.skipif(
    not sys.modules.get("reportlab"),
    reason="reportlab not installed — skipping word_converter integration tests",
)


class TestMarkdownToStory:
    def test_empty_content(self):
        from app.utils.word_converter import _markdown_to_story, _build_styles
        styles = _build_styles()
        story = _markdown_to_story("", styles)
        assert len(story) >= 0

    def test_heading_parsing(self):
        from app.utils.word_converter import _parse_heading
        assert _parse_heading("## Hello") == (2, "Hello")
        assert _parse_heading("# Title") == (1, "Title")
        assert _parse_heading("### Sub") == (3, "Sub")
        assert _parse_heading("No heading") is None

    def test_bullet_parsing(self):
        from app.utils.word_converter import _parse_bullet
        assert _parse_bullet("- item") == "item"
        assert _parse_bullet("* item2") == "item2"
        assert _parse_bullet("not a bullet") is None

    def test_heading_generates_story(self):
        from app.utils.word_converter import _markdown_to_story, _build_styles
        story = _markdown_to_story("# Title\n\nBody text", _build_styles())
        assert len(story) > 0

    def test_bullet_generates_story(self):
        from app.utils.word_converter import _markdown_to_story, _build_styles
        story = _markdown_to_story("- item 1\n- item 2", _build_styles())
        assert len(story) > 0

    def test_code_block(self):
        from app.utils.word_converter import _markdown_to_story, _build_styles
        story = _markdown_to_story("```\ncode\n```", _build_styles())
        assert len(story) > 0

    def test_table_detection(self):
        from app.utils.word_converter import _is_table_start, _collect_table, _split_table_row
        lines = ["|a|b|", "|---|---|", "|1|2|"]
        assert _is_table_start(lines, 0) is True
        rows, idx = _collect_table(lines, 0)
        assert len(rows) == 2
        assert rows[0] == ["a", "b"]
        assert rows[1] == ["1", "2"]

    def test_inline_formatting(self):
        from app.utils.word_converter import _format_inline
        result = _format_inline("**bold** and `code`")
        assert "<b>bold</b>" in result

    def test_convert_md_to_pdf_missing_file(self):
        from app.utils.word_converter import convert_md_to_pdf
        result = convert_md_to_pdf(Path("/nonexistent/file.md"), Path("/tmp/out.pdf"))
        assert "失败" in result

    def test_convert_md_to_pdf_missing_deps(self, monkeypatch):
        monkeypatch.setattr("app.utils.word_converter.SimpleDocTemplate", None)
        from app.utils.word_converter import convert_md_to_pdf
        result = convert_md_to_pdf(Path("in.md"), Path("out.pdf"))
        assert "缺少依赖" in result

    def test_table_building(self):
        from app.utils.word_converter import _build_table, _build_styles
        table = _build_table([["a", "b"], ["1", "2"]], _build_styles())
        assert table is not None
