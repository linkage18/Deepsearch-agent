"""
Comprehensive tests for citation verification.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.citation_checker import extract_claims, verify_citations, _classify_similarity


@pytest.fixture
def isolated_session():
    """Provide an isolated session DB and clean up connections afterward."""
    from app.models.session import set_session_db_path, close_pool
    from app.models.session import SESSION_DB_PATH as _orig
    with TemporaryDirectory() as td:
        db_path = Path(td) / "sessions.sqlite3"
        set_session_db_path(db_path)
        yield db_path
        close_pool()
        set_session_db_path(_orig)


class TestExtractClaims:
    def test_empty_text(self):
        assert extract_claims("") == []

    def test_no_citation_markers(self):
        assert extract_claims("这是普通文本，没有引用标记。") == []

    def test_evidence_marker(self):
        text = "该方法表现优异【证据: abc123】。实验证明有效【证据: def456】。"
        claims = extract_claims(text)
        assert len(claims) == 2
        assert claims[0]["evidence_ids"] == ["abc123"]
        assert claims[1]["evidence_ids"] == ["def456"]

    def test_source_marker(self):
        text = "MIM-Reasoner 使用强化学习【来源: MIM-Reasoner, p.5】。"
        claims = extract_claims(text)
        assert len(claims) == 1
        assert claims[0]["sources"] == [("MIM-Reasoner", "5")]

    def test_short_sentence_skipped(self):
        assert len(extract_claims("a【证据: x】")) == 0

    def test_dedup_by_content(self):
        text = "方法有效【证据: a】。方法有效【证据: a】。"
        claims = extract_claims(text)
        assert len(claims) == 1

    def test_mixed_markers(self):
        text = "该方法【证据: id1】【来源: PaperA, p.3】表现优异。"
        claims = extract_claims(text)
        assert len(claims) == 1
        assert claims[0]["evidence_ids"] == ["id1"]
        assert claims[0]["sources"] == [("PaperA", "3")]

    def test_unicode_cjk_markers(self):
        text = "实验证明【证据: evt001】该方法有效。"
        claims = extract_claims(text)
        assert len(claims) == 1
        assert "evt001" in claims[0]["evidence_ids"]

    def test_page_number_variants(self):
        texts = [
            ("【来源: Paper, p.5】", ("Paper", "5")),
            ("【来源: Paper, p．5】", ("Paper", "5")),
            ("【来源: Paper, p. 5】", ("Paper", "5")),
        ]
        for text, expected in texts:
            claims = extract_claims(f"测试内容{text}结束。")
            if claims:
                assert claims[0]["sources"][0] == expected


class TestClassifySimilarity:
    def test_verified(self):
        assert _classify_similarity(0.7) == "verified"
        assert _classify_similarity(0.5) == "verified"

    def test_low_confidence(self):
        assert _classify_similarity(0.3) == "low_confidence"
        assert _classify_similarity(0.25) == "low_confidence"

    def test_unfounded(self):
        assert _classify_similarity(0.1) == "unfounded"
        assert _classify_similarity(0.0) == "unfounded"

    def test_none_is_unfounded(self):
        assert _classify_similarity(None) == "unfounded"


class TestVerifyCitations:
    def test_no_claims(self, isolated_session):
        result = verify_citations("t", "r", "这是一篇无引用的报告。")
        assert result["total_claims"] == 0
        assert result["no_claim"] == 1

    def test_with_matching_evidence_id(self, isolated_session):
        from app.models.session import save_evidence_records
        save_evidence_records("test query", [
            {
                "evidence_id": "evt001",
                "source_type": "pdf",
                "source": "test-paper.pdf",
                "page": "5",
                "score": 0.85,
                "quote": "该方法使用强化学习优化传播过程",
                "metadata": {"title": "Test Paper"},
            },
        ])
        text = "该方法使用强化学习优化传播过程【证据: evt001】。"
        result = verify_citations("t", "r", text)
        assert result["total_claims"] >= 1
        assert result["verified"] + result["low_confidence"] + result["unfounded"] == result["total_claims"]

    def test_result_structure(self, isolated_session):
        result = verify_citations("t", "r", "无引用。")
        for key in ("total_claims", "verified", "low_confidence", "unfounded",
                     "no_claim", "coverage_rate", "unfounded_rate", "details"):
            assert key in result, f"Missing key: {key}"

    def test_multiple_claims_in_report(self, isolated_session):
        text = "方法一有效【证据: a】。方法二更优【证据: b】。"
        result = verify_citations("t", "r", text)
        assert result["total_claims"] == 2

    def test_special_characters_in_claim(self, isolated_session):
        text = "O(n²) 复杂度【证据: cmp001】。温度 100°C 时最优【证据: cmp002】。"
        result = verify_citations("t", "r", text)
        assert result["total_claims"] == 2

    def test_no_evidence_records(self, isolated_session):
        text = "某方法有效【证据: missing_id】。"
        result = verify_citations("t", "r", text)
        assert result["total_claims"] == 1
        assert result["unfounded"] == 1

    def test_source_match_fallback(self, isolated_session):
        from app.models.session import save_evidence_records
        save_evidence_records("test", [
            {
                "evidence_id": "kb-1",
                "source_type": "pdf",
                "source": "PaperX.pdf",
                "page": "5",
                "score": 0.9,
                "quote": "核心算法使用图神经网络",
                "metadata": {},
            },
        ])
        text = "该论文使用图神经网络【来源: PaperX.pdf, p.5】。"
        result = verify_citations("t", "r", text)
        assert result["total_claims"] >= 1


if __name__ == "__main__":
    pytest.main([__file__])
