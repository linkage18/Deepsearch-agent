"""Utilities for turning retrieved evidence into reusable paper cards."""

import hashlib
from typing import Any


FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "problem": (
        "problem",
        "challenge",
        "motivation",
        "研究问题",
        "挑战",
        "动机",
    ),
    "method": (
        "method",
        "approach",
        "model",
        "framework",
        "algorithm",
        "方法",
        "模型",
        "框架",
        "算法",
    ),
    "experiment": (
        "experiment",
        "dataset",
        "benchmark",
        "evaluation",
        "metric",
        "实验",
        "数据集",
        "评测",
        "指标",
    ),
    "conclusion": (
        "result",
        "outperform",
        "improve",
        "conclusion",
        "finding",
        "结果",
        "提升",
        "结论",
        "发现",
    ),
    "limitation": (
        "limitation",
        "future work",
        "fail",
        "weakness",
        "局限",
        "不足",
        "未来工作",
    ),
}


def _first_source(evidence: list[dict[str, Any]]) -> str:
    for item in evidence:
        source = str(item.get("source", "")).strip()
        if source:
            return source
    return ""


def _quote(item: dict[str, Any]) -> str:
    return " ".join(str(item.get("quote", "")).split())


def _classify_evidence(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    fields: dict[str, list[dict[str, Any]]] = {key: [] for key in FIELD_KEYWORDS}
    fields["summary"] = []

    for item in evidence:
        quote = _quote(item)
        lowered = quote.lower()
        matched = False
        for field, keywords in FIELD_KEYWORDS.items():
            if any(keyword.lower() in lowered for keyword in keywords):
                fields[field].append(item)
                matched = True
        if not matched:
            fields["summary"].append(item)

    fallback = evidence[:3]
    if not fields["summary"]:
        fields["summary"] = fallback
    return fields


def _excerpts(items: list[dict[str, Any]], limit: int = 2) -> list[str]:
    values = []
    for item in items[:limit]:
        quote = _quote(item)
        if quote:
            values.append(quote[:360])
    return values


def build_paper_card_from_evidence(
    title: str,
    query: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic paper card from structured retrieval evidence."""
    clean_title = title.strip() or _first_source(evidence) or query.strip()
    source = _first_source(evidence)
    grouped = _classify_evidence(evidence)
    digest_raw = "|".join(
        [
            clean_title,
            source,
            *[str(item.get("evidence_id", "")) for item in evidence],
            *[_quote(item)[:120] for item in evidence[:3]],
        ]
    )
    card_id = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()[:16]

    fields = {
        "problem": _excerpts(grouped["problem"]),
        "method": _excerpts(grouped["method"]),
        "experiment": _excerpts(grouped["experiment"]),
        "conclusion": _excerpts(grouped["conclusion"]),
        "limitation": _excerpts(grouped["limitation"]),
        "summary": _excerpts(grouped["summary"], limit=3),
        "status": "auto_extracted" if evidence else "no_evidence",
    }

    return {
        "card_id": card_id,
        "title": clean_title,
        "source": source,
        "query": query,
        "fields": fields,
        "evidence": evidence,
    }
