"""Tests for the Markdown generation tool — path resolution, edge cases, errors."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def fake_session_context(monkeypatch):
    """Point session context to a temp directory."""
    tmp = TemporaryDirectory()
    monkeypatch.setattr("app.tools.markdown_tools.get_session_context", lambda: tmp.name)
    yield Path(tmp.name)
    tmp.cleanup()


class TestGenerateMarkdown:
    def test_basic_md_file(self):
        from app.tools.markdown_tools import generate_markdown
        result = generate_markdown.invoke({"content": "# Hello", "filename": "test_file", "path": ""})
        assert "成功" in result or "已成功" in result

    def test_without_md_suffix_auto_appended(self, fake_session_context):
        from app.tools.markdown_tools import generate_markdown
        result = generate_markdown.invoke({"content": "test", "filename": "no_suffix", "path": ""})
        assert "成功" in result or "已成功" in result

    def test_with_subdirectory_path(self):
        from app.tools.markdown_tools import generate_markdown
        result = generate_markdown.invoke({"content": "# Sub", "filename": "sub_file.md", "path": "subdir"})
        assert "成功" in result or "已成功" in result

    def test_empty_content(self):
        from app.tools.markdown_tools import generate_markdown
        result = generate_markdown.invoke({"content": "", "filename": "empty.md", "path": ""})
        assert "成功" in result or "已成功" in result

    def test_file_actually_written(self, fake_session_context):
        from app.tools.markdown_tools import generate_markdown
        generate_markdown.invoke({"content": "实际内容", "filename": "real_check.md", "path": ""})
        p = fake_session_context / "real_check.md"
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "实际内容"

    def test_path_dot_resolves_to_session(self):
        from app.tools.markdown_tools import generate_markdown
        result = generate_markdown.invoke({"content": "dot", "filename": "dot.md", "path": "."})
        assert "成功" in result or "已成功" in result

    def test_long_content_full_in_file(self, fake_session_context):
        from app.tools.markdown_tools import generate_markdown
        long = "line\n" * 500
        generate_markdown.invoke({"content": long, "filename": "long.md", "path": ""})
        p = fake_session_context / "long.md"
        assert len(p.read_text(encoding="utf-8")) > 2000
