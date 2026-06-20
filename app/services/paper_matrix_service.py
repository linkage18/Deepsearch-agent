"""Build comparison matrix views from structured paper cards."""

from typing import Any


MATRIX_COLUMNS = [
    {"key": "title", "label": "论文"},
    {"key": "problem", "label": "研究问题"},
    {"key": "method", "label": "核心方法"},
    {"key": "experiment", "label": "实验设置"},
    {"key": "conclusion", "label": "主要结论"},
    {"key": "limitation", "label": "局限性"},
    {"key": "evidence_count", "label": "证据数"},
]


def _join_field(fields: dict[str, Any], key: str) -> str:
    value = fields.get(key)
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(cleaned[:2]) if cleaned else "待补充"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "待补充"


def build_paper_matrix(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Transform PaperCard records into a deterministic comparison matrix."""
    rows = []
    for card in cards:
        fields = card.get("fields", {}) or {}
        evidence = card.get("evidence", []) or []
        rows.append(
            {
                "card_id": card.get("card_id", ""),
                "title": card.get("title", ""),
                "source": card.get("source", ""),
                "problem": _join_field(fields, "problem"),
                "method": _join_field(fields, "method"),
                "experiment": _join_field(fields, "experiment"),
                "conclusion": _join_field(fields, "conclusion"),
                "limitation": _join_field(fields, "limitation"),
                "evidence_count": len(evidence),
                "created_at": card.get("created_at", ""),
            }
        )
    return {
        "columns": MATRIX_COLUMNS,
        "rows": rows,
        "card_count": len(rows),
    }
