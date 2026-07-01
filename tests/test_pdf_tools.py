"""Tests for the Markdown→PDF conversion tool — path resolution, error handling."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def session_with_source(monkeypatch):
    """Set up session context and create a source.md for tests."""
    tmp = TemporaryDirectory()
    monkeypatch.setattr("app.tools.pdf_tools.get_session_context", lambda: tmp.name)
    (Path(tmp.name) / "source.md").write_text("# Test\nContent", encoding="utf-8")
    yield tmp
    tmp.cleanup()


class TestConvertMdToPdf:
    def test_missing_file_returns_error(self):
        from app.tools.pdf_tools import convert_md_to_pdf
        result = convert_md_to_pdf.invoke({"md_filename": "nonexistent.md"})
        assert "错误" in result or "不存在" in result

    def test_filename_without_suffix_auto_appended(self):
        from app.tools.pdf_tools import convert_md_to_pdf
        result = convert_md_to_pdf.invoke({"md_filename": "source"})
        assert "错误" not in result

    def test_with_custom_pdf_filename(self):
        from app.tools.pdf_tools import convert_md_to_pdf
        result = convert_md_to_pdf.invoke({"md_filename": "source.md", "pdf_filename": "custom.pdf"})
        assert "错误" not in result

    def test_pdf_filename_without_suffix_auto_appended(self):
        from app.tools.pdf_tools import convert_md_to_pdf
        result = convert_md_to_pdf.invoke({"md_filename": "source.md", "pdf_filename": "output"})
        assert "错误" not in result

    def test_empty_md_filename_returns_error(self):
        from app.tools.pdf_tools import convert_md_to_pdf
        result = convert_md_to_pdf.invoke({"md_filename": ""})
        assert "错误" in result or "不存在" in result or "失败" in result

    def test_pdf_defaults_to_same_name_as_md(self, monkeypatch):
        with TemporaryDirectory() as td:
            monkeypatch.setattr("app.tools.pdf_tools.get_session_context", lambda: td)
            (Path(td) / "mytest.md").write_text("# Hello", encoding="utf-8")
            from app.tools.pdf_tools import convert_md_to_pdf
            result = convert_md_to_pdf.invoke({"md_filename": "mytest.md"})
            assert "成功" in result or "转换" in result
