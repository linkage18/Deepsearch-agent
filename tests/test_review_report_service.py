"""Tests for the review report service — markdown rendering, file output, edge cases."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _matrix_row(title="Paper", method="GNN", problem="Overfitting", experiment="ImageNet",
                conclusion="SOTA", limitation="Speed", evidence_count=1):
    return {
        "title": title,
        "source": "paper.pdf",
        "problem": problem,
        "method": method,
        "experiment": experiment,
        "conclusion": conclusion,
        "limitation": limitation,
        "evidence_count": evidence_count,
    }


class TestReviewMarkdown:
    def test_basic_md_structure(self):
        from app.services.review_report_service import build_review_markdown
        md = build_review_markdown("Test Review", {"rows": [_matrix_row()], "card_count": 1})
        assert "# Test Review" in md
        assert "## 1." in md
        assert "## 7." in md

    def test_empty_cards_still_renders(self):
        from app.services.review_report_service import build_review_markdown
        md = build_review_markdown("Empty Review", {"rows": [], "card_count": 0})
        assert "暂无" in md

    def test_section_from_rows_present(self):
        from app.services.review_report_service import _section_from_rows
        rows = [_matrix_row(method="Graph Neural Networks")]
        section = _section_from_rows(rows, "method")
        assert "Graph Neural Networks" in section
        assert "Paper" in section

    def test_section_all_placeholder(self):
        from app.services.review_report_service import _section_from_rows
        rows = [{"title": "Paper", "method": "待补充"}]
        section = _section_from_rows(rows, "method")
        assert "暂无" in section

    def test_safe_filename_cleans_value(self):
        from app.services.review_report_service import _safe_filename
        name = _safe_filename("hello!@#$world")
        assert "hello" in name
        assert len(name) <= 48

    def test_escape_table(self):
        from app.services.review_report_service import _escape_table
        result = _escape_table("a | b")
        assert "\\|" in result

    def test_write_report_creates_file(self):
        from app.services.review_report_service import write_review_report
        import app.config.paths
        with TemporaryDirectory() as td:
            orig = app.config.paths.REPORT_DIR
            app.config.paths.REPORT_DIR = Path(td)
            try:
                result = write_review_report("Topic", [], thread_id="test-001")
                assert result["card_count"] == 0
                assert result["name"].endswith(".md")
                assert Path(result["path"]).exists()
            finally:
                app.config.paths.REPORT_DIR = orig

    def test_write_report_with_cards(self):
        from app.services.review_report_service import write_review_report
        import app.config.paths
        with TemporaryDirectory() as td:
            orig = app.config.paths.REPORT_DIR
            app.config.paths.REPORT_DIR = Path(td)
            try:
                result = write_review_report("Methods Review", [
                    {"card_id": "c1", "title": "Paper", "source": "s.pdf",
                     "fields": {"method": ["GNN"]}, "evidence": [], "created_at": ""}
                ], thread_id="test-002")
                assert result["card_count"] == 1
            finally:
                app.config.paths.REPORT_DIR = orig

    def test_empty_topic_defaults(self):
        from app.services.review_report_service import build_review_markdown
        md = build_review_markdown("", {"rows": [], "card_count": 0})
        assert "论文综述报告" in md or "review" in md.lower()
