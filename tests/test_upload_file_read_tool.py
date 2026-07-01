"""Tests for the upload file reading tool — mock file types, missing deps, errors."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def session_and_ctx(monkeypatch):
    """Single temp dir for both session context and file writes.

    Must patch at the tool module level, since upload_file_read_tool imports
    get_session_context as a local reference.
    """
    tmp = TemporaryDirectory()
    monkeypatch.setattr("app.tools.upload_file_read_tool.get_session_context", lambda: tmp.name)
    yield Path(tmp.name)
    tmp.cleanup()


class TestReadFileContent:
    def test_missing_file(self):
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "ghost.md"})
        assert "不存在" in result

    def test_read_markdown(self, session_and_ctx):
        (session_and_ctx / "test.md").write_text("# Markdown Content", encoding="utf-8")
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "test.md"})
        assert "# Markdown Content" in result

    def test_read_txt(self, session_and_ctx):
        (session_and_ctx / "notes.txt").write_text("Plain text content", encoding="utf-8")
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "notes.txt"})
        assert "Plain text" in result

    def test_docx_missing_dependency(self, monkeypatch, session_and_ctx):
        (session_and_ctx / "doc.docx").write_text("fake docx", encoding="utf-8")
        monkeypatch.setattr("app.tools.upload_file_read_tool.docx", None)
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "doc.docx"})
        assert "未安装" in result

    def test_pdf_missing_dependency(self, monkeypatch, session_and_ctx):
        (session_and_ctx / "doc.pdf").write_text("fake pdf", encoding="utf-8")
        monkeypatch.setattr("app.tools.upload_file_read_tool.pypdf", None)
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "doc.pdf"})
        assert "未安装" in result

    def test_excel_missing_dependency(self, monkeypatch, session_and_ctx):
        (session_and_ctx / "data.xlsx").write_text("fake xlsx", encoding="utf-8")
        monkeypatch.setattr("app.tools.upload_file_read_tool.pd", None)
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "data.xlsx"})
        assert "未安装" in result or "错误" in result or "支持" in result

    def test_unsupported_extension_falls_back_to_text(self, session_and_ctx):
        (session_and_ctx / "data.csv").write_text("a,b,c\n1,2,3", encoding="utf-8")
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "data.csv"})
        assert "a,b,c" in result

    def test_binary_file_fallback(self, session_and_ctx):
        # Small control-byte sequences are valid UTF-8; tool reads them as text
        (session_and_ctx / "data.bin").write_bytes(b"\x00\x01\x02\x03")
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "data.bin"})
        assert result is not None

    def test_with_custom_instruction(self, session_and_ctx):
        (session_and_ctx / "report.md").write_text("# Report", encoding="utf-8")
        from app.tools.upload_file_read_tool import read_file_content
        result = read_file_content.invoke({"filename": "report.md", "instruction": "提取摘要"})
        assert "# Report" in result

    def test_empty_filename_raises(self):
        from app.tools.upload_file_read_tool import read_file_content
        with pytest.raises(ValueError):
            read_file_content.invoke({"filename": ""})
