"""Tests for the paper card service — evidence classification, card building."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_evidence(quote: str, source: str = "paper.pdf", eid: str = "e1") -> dict:
    return {"evidence_id": eid, "source_type": "pdf", "source": source,
            "page": "3", "score": 0.85, "quote": quote, "metadata": {}}


class TestClassifyEvidence:
    def test_method_keyword_matches(self):
        from app.services.paper_card_service import _classify_evidence
        ev = [_make_evidence("We propose a new GNN method for classification")]
        grouped = _classify_evidence(ev)
        assert len(grouped["method"]) == 1

    def test_problem_keyword_matches(self):
        from app.services.paper_card_service import _classify_evidence
        ev = [_make_evidence("The main challenge is scalability")]
        grouped = _classify_evidence(ev)
        assert len(grouped["problem"]) == 1

    def test_no_match_goes_to_summary_fallback(self):
        from app.services.paper_card_service import _classify_evidence
        ev = [_make_evidence("Some unrelated content here")]
        grouped = _classify_evidence(ev)
        assert len(grouped["summary"]) >= 1

    def test_mixed_evidence_classified_correctly(self):
        from app.services.paper_card_service import _classify_evidence
        evs = [
            _make_evidence("The problem of overfitting", source="a.pdf", eid="e1"),
            _make_evidence("Our method uses attention", source="a.pdf", eid="e2"),
            _make_evidence("Experiments on ImageNet", source="a.pdf", eid="e3"),
        ]
        grouped = _classify_evidence(evs)
        assert len(grouped["problem"]) >= 1
        assert len(grouped["method"]) >= 1
        assert len(grouped["experiment"]) >= 1


class TestBuildPaperCardFromEvidence:
    def test_basic_card_creation(self):
        from app.services.paper_card_service import build_paper_card_from_evidence
        evs = [_make_evidence("Our method achieves SOTA results", source="paper.pdf")]
        card = build_paper_card_from_evidence("Test Paper", "test query", evs)
        assert card["card_id"]
        assert card["title"] == "Test Paper"
        assert card["source"] == "paper.pdf"
        assert "status" in card["fields"]

    def test_empty_title_uses_source(self):
        from app.services.paper_card_service import build_paper_card_from_evidence
        evs = [_make_evidence("content", source="mypaper.pdf")]
        card = build_paper_card_from_evidence("", "query", evs)
        assert card["title"] == "mypaper.pdf"

    def test_empty_evidence_sets_no_evidence_status(self):
        from app.services.paper_card_service import build_paper_card_from_evidence
        card = build_paper_card_from_evidence("Title", "query", [])
        assert card["fields"]["status"] == "no_evidence"

    def test_deterministic_card_id(self):
        from app.services.paper_card_service import build_paper_card_from_evidence
        evs = [_make_evidence("content", source="p.pdf")]
        card1 = build_paper_card_from_evidence("Title", "query", evs)
        card2 = build_paper_card_from_evidence("Title", "query", evs)
        assert card1["card_id"] == card2["card_id"]

    def test_chinese_keyword_matches(self):
        from app.services.paper_card_service import _classify_evidence
        ev = [_make_evidence("本文方法基于图神经网络框架")]
        grouped = _classify_evidence(ev)
        assert len(grouped["method"]) >= 1

    def test_first_source_returns_first_non_empty(self):
        from app.services.paper_card_service import _first_source
        evs = [
            {"evidence_id": "e1", "source": "", "quote": "a"},
            {"evidence_id": "e2", "source": "real.pdf", "quote": "b"},
        ]
        assert _first_source(evs) == "real.pdf"

    def test_first_source_empty_for_empty_list(self):
        from app.services.paper_card_service import _first_source
        assert _first_source([]) == ""

    def test_excerpts_limits_items(self):
        from app.services.paper_card_service import _excerpts
        items = [{"quote": "a"}, {"quote": "b"}, {"quote": "c"}]
        result = _excerpts(items, limit=2)
        assert len(result) == 2

    def test_excerpts_skips_empty_quotes(self):
        from app.services.paper_card_service import _excerpts
        items = [{"quote": ""}, {"quote": "content"}]
        result = _excerpts(items)
        assert result == ["content"]
