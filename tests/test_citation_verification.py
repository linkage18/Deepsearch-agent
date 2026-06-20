"""
Tests for citation verification module (extraction + verification pipeline).
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.tools.citation_checker import extract_claims, verify_citations


def test_extract_claims_empty() -> None:
    assert extract_claims("") == []
    assert extract_claims("普通文本，没有引用标记。") == []


def test_extract_claims_evidence_marker() -> None:
    text = "该方法表现优异【证据: abc123】。实验证明有效【证据: def456】。"
    claims = extract_claims(text)
    assert len(claims) == 2
    assert claims[0]["evidence_ids"] == ["abc123"]
    assert claims[1]["evidence_ids"] == ["def456"]


def test_extract_claims_source_marker() -> None:
    text = "MIM-Reasoner 使用强化学习【来源: MIM-Reasoner, p.5】。"
    claims = extract_claims(text)
    assert len(claims) == 1
    assert claims[0]["sources"][0] == ("MIM-Reasoner", "5")


def test_extract_claims_short_sentence_skipped() -> None:
    # 8 chars, below 10 threshold
    assert len(extract_claims("a【证据: x】")) == 0
    # 9 chars, still below 10
    assert len(extract_claims("ab【证据:】")) == 0


def test_verify_citations_no_claims() -> None:
    result = verify_citations("t", "r", "这是一篇无引用的报告。")
    assert result["total_claims"] == 0
    assert result["no_claim"] == 1


def test_verify_citations_with_matching_evidence() -> None:
    from app.models.session import save_evidence_records, set_session_db_path

    with TemporaryDirectory() as td:
        set_session_db_path(Path(td) / "sessions.sqlite3")
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


def test_verify_citations_stats_structure() -> None:
    from app.models.session import set_session_db_path

    with TemporaryDirectory() as td:
        set_session_db_path(Path(td) / "sessions.sqlite3")
        result = verify_citations("t", "r", "无引用。")
        for key in ("total_claims", "verified", "low_confidence", "unfounded",
                     "no_claim", "coverage_rate", "unfounded_rate", "details"):
            assert key in result, f"Missing key: {key}"


if __name__ == "__main__":
    tests = [
        ("empty", test_extract_claims_empty),
        ("evidence_marker", test_extract_claims_evidence_marker),
        ("source_marker", test_extract_claims_source_marker),
        ("short_skipped", test_extract_claims_short_sentence_skipped),
        ("no_claims", test_verify_citations_no_claims),
        ("with_evidence", test_verify_citations_with_matching_evidence),
        ("stats_structure", test_verify_citations_stats_structure),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name}: {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(0 if failed == 0 else 1)
