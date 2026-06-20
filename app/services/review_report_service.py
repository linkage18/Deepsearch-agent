"""Generate Markdown review reports from paper comparison matrices."""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.paths import REPORT_DIR
from app.services.paper_matrix_service import build_paper_matrix


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")[:48]
    return cleaned or "review"


def _escape_table(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _section_from_rows(rows: list[dict[str, Any]], key: str) -> str:
    bullets = []
    for row in rows:
        value = str(row.get(key, "")).strip()
        if value and value != "待补充":
            bullets.append(f"- **{row.get('title', '未知论文')}**：{value}")
    return "\n".join(bullets) if bullets else "- 暂无足够证据，需要继续补充论文卡片或人工核验。"


def build_review_markdown(topic: str, matrix: dict[str, Any]) -> str:
    """Render a deterministic Markdown literature review from a paper matrix."""
    rows = matrix.get("rows", [])
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# {topic.strip() or '论文综述报告'}",
        "",
        f"> 生成时间：{generated_at}",
        f"> 纳入论文：{len(rows)} 篇",
        "",
        "## 1. 研究对象与资料范围",
        "",
        (
            f"本报告基于系统中最近沉淀的 {len(rows)} 张论文卡片生成。"
            "卡片由论文库证据片段抽取而来，适合作为综述初稿和人工核验底稿。"
        ),
        "",
        "## 2. 论文对比矩阵",
        "",
        "| 论文 | 研究问题 | 核心方法 | 实验设置 | 主要结论 | 局限性 | 证据数 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_table(str(row.get("title", ""))),
                        _escape_table(str(row.get("problem", ""))),
                        _escape_table(str(row.get("method", ""))),
                        _escape_table(str(row.get("experiment", ""))),
                        _escape_table(str(row.get("conclusion", ""))),
                        _escape_table(str(row.get("limitation", ""))),
                        str(row.get("evidence_count", 0)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| 暂无 | 待补充 | 待补充 | 待补充 | 待补充 | 待补充 | 0 |")

    lines.extend(
        [
            "",
            "## 3. 方法脉络",
            "",
            _section_from_rows(rows, "method"),
            "",
            "## 4. 实验与评测对比",
            "",
            _section_from_rows(rows, "experiment"),
            "",
            "## 5. 主要结论",
            "",
            _section_from_rows(rows, "conclusion"),
            "",
            "## 6. 局限性与后续工作",
            "",
            _section_from_rows(rows, "limitation"),
            "",
            "## 7. 核验说明",
            "",
            (
                "- 本报告由结构化论文卡片和证据片段自动生成，不等同于最终人工定稿。\n"
                "- 标记为“待补充”的字段说明当前证据不足，应继续检索原文或人工补录。\n"
                "- 正式引用前应回到 EvidenceRecord 中的原文片段、页码和来源文件进行核验。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_review_report(
    topic: str,
    cards: list[dict[str, Any]],
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build and persist a Markdown review report under REPORT_DIR."""
    matrix = build_paper_matrix(cards)
    markdown = build_review_markdown(topic, matrix)
    session_name = f"session_{thread_id}" if thread_id else "matrix_reports"
    target_dir = (REPORT_DIR / session_name).resolve()
    report_root = REPORT_DIR.resolve()
    if not target_dir.is_relative_to(report_root):
        raise ValueError("非法报告目录")

    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{_safe_filename(topic)}_{timestamp}.md"
    path = target_dir / filename
    path.write_text(markdown, encoding="utf-8")
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "card_count": matrix["card_count"],
        "markdown": markdown,
    }
