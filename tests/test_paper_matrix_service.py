"""Tests for the paper matrix service — edge cases, field joining, rendering."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_card(card_id="c1", title="Paper", fields=None, evidence=None, source="src.pdf"):
    return {
        "card_id": card_id,
        "title": title,
        "source": source,
        "fields": fields or {},
        "evidence": evidence or [],
        "created_at": "2025-01-01T00:00:00",
    }


class TestPaperMatrix:
    def test_empty_cards(self):
        from app.services.paper_matrix_service import build_paper_matrix
        result = build_paper_matrix([])
        assert result["rows"] == []
        assert result["card_count"] == 0
        assert len(result["columns"]) > 0

    def test_single_card(self):
        from app.services.paper_matrix_service import build_paper_matrix
        card = _make_card(fields={"method": ["GNN", "Attention"], "problem": ["Overfitting"]})
        result = build_paper_matrix([card])
        assert result["card_count"] == 1
        assert "GNN" in result["rows"][0]["method"]

    def test_multiple_cards(self):
        from app.services.paper_matrix_service import build_paper_matrix
        cards = [
            _make_card("c1", "Paper A", fields={"method": ["GNN"]}),
            _make_card("c2", "Paper B", fields={"method": ["CNN"]}),
        ]
        result = build_paper_matrix(cards)
        assert result["card_count"] == 2

    def test_evidence_count(self):
        from app.services.paper_matrix_service import build_paper_matrix
        card = _make_card(evidence=[{"quote": "a"}, {"quote": "b"}])
        result = build_paper_matrix([card])
        assert result["rows"][0]["evidence_count"] == 2

    def test_join_field_list(self):
        from app.services.paper_matrix_service import _join_field
        assert "A" in _join_field({"method": ["A", "B"]}, "method")

    def test_join_field_string(self):
        from app.services.paper_matrix_service import _join_field
        assert _join_field({"method": "Single method"}, "method") == "Single method"

    def test_join_field_missing_returns_placeholder(self):
        from app.services.paper_matrix_service import _join_field
        assert _join_field({}, "method") == "待补充"

    def test_join_field_empty_list_returns_placeholder(self):
        from app.services.paper_matrix_service import _join_field
        assert _join_field({"method": []}, "method") == "待补充"

    def test_row_contains_evidence_count(self):
        from app.services.paper_matrix_service import build_paper_matrix
        card = _make_card()
        result = build_paper_matrix([card])
        assert "evidence_count" in result["rows"][0]

    def test_column_labels_match_expected(self):
        from app.services.paper_matrix_service import MATRIX_COLUMNS
        labels = [c["label"] for c in MATRIX_COLUMNS]
        assert "论文" in labels
        assert "核心方法" in labels

    def test_none_fields_handled(self):
        from app.services.paper_matrix_service import build_paper_matrix
        card = _make_card(fields=None)
        result = build_paper_matrix([card])
        assert result["rows"][0]["method"] == "待补充"
