"""
Session metadata store backed by SQLite.

The original JSON file store loses updates under concurrent writes. SQLite gives
this single-node project durable writes and transaction isolation without adding
an external database service.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from app.config.paths import SESSIONS_DB_PATH


SESSION_DB_PATH = SESSIONS_DB_PATH
_init_lock = threading.Lock()
_initialized_paths: set[Path] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    resolved = SESSION_DB_PATH.resolve()
    if resolved in _initialized_paths:
        return
    with _init_lock:
        if resolved in _initialized_paths:
            return
        conn = sqlite3.connect(str(SESSION_DB_PATH), timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    query_preview TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    turns_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_run_events_thread_created
                ON run_events(thread_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT,
                    query TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    page TEXT,
                    score REAL,
                    quote TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evidence_query_created
                ON evidence_records(query, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS citation_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT,
                    report_id TEXT,
                    claim_snippet TEXT NOT NULL,
                    claimed_evidence_id TEXT,
                    matched_evidence_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    similarity_score REAL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_citation_checks_thread
                ON citation_checks(thread_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id TEXT NOT NULL,
                    thread_id TEXT,
                    title TEXT NOT NULL,
                    source TEXT,
                    query TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_paper_cards_created
                ON paper_cards(created_at)
                """
            )
            _initialized_paths.add(resolved)
        finally:
            conn.close()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _ensure_schema()
    conn = sqlite3.connect(str(SESSION_DB_PATH), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
    finally:
        conn.close()


def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    try:
        turns = json.loads(row["turns_json"] or "[]")
    except json.JSONDecodeError:
        turns = []
    return {
        "id": row["id"],
        "title": row["title"],
        "query_preview": row["query_preview"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "file_count": row["file_count"],
        "completed": bool(row["completed"]),
        "turns": turns,
    }


def save_session(session_id: str, query: str) -> None:
    """Create a session record if it does not already exist."""
    now = _now()
    title = query.strip()[:30]
    if len(query) > 30:
        title += "..."

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
            (id, title, query_preview, created_at, updated_at, file_count, completed, turns_json)
            VALUES (?, ?, ?, ?, ?, 0, 0, '[]')
            """,
            (session_id, title, query[:100], now, now),
        )


def append_turn(session_id: str, query: str, result: str) -> None:
    """Append one conversation turn, keeping the newest 20 turns."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT turns_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            conn.execute("COMMIT")
            return
        try:
            turns = json.loads(row["turns_json"] or "[]")
        except json.JSONDecodeError:
            turns = []
        turns.append({"query": query[:200], "result": result[:2000]})
        turns = turns[-20:]
        conn.execute(
            "UPDATE sessions SET turns_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(turns, ensure_ascii=False), _now(), session_id),
        )
        conn.execute("COMMIT")


def update_session(session_id: str, **kwargs: Any) -> None:
    """Update supported session metadata fields."""
    allowed = {"file_count", "completed", "title", "query_preview", "turns"}
    updates: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "completed":
            updates[key] = 1 if value else 0
        elif key == "turns":
            updates["turns_json"] = json.dumps(value, ensure_ascii=False)
        else:
            updates[key] = value

    if not updates:
        return

    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [session_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE sessions SET {assignments} WHERE id = ?",
            values,
        )


def list_sessions() -> list[dict[str, Any]]:
    """Return all sessions ordered by latest update first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_session(row) for row in rows]


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_session(row) if row else None


def delete_session(session_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return cursor.rowcount > 0


def save_run_event(
    thread_id: str | None,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Persist a monitor event for later replay or debugging."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO run_events (thread_id, event_type, message, data_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                event_type,
                message,
                json.dumps(data or {}, ensure_ascii=False, default=str),
                _now(),
            ),
        )


def list_run_events(thread_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return recent monitor events for one thread."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event_type, message, data_json, created_at
            FROM run_events
            WHERE thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (thread_id, limit),
        ).fetchall()

    events = []
    for row in reversed(rows):
        try:
            data = json.loads(row["data_json"] or "{}")
        except json.JSONDecodeError:
            data = {}
        events.append(
            {
                "type": "monitor_event",
                "event": row["event_type"],
                "message": row["message"],
                "data": data,
                "timestamp": row["created_at"],
            }
        )
    return events


def save_evidence_records(
    query: str,
    evidence: list[dict[str, Any]],
    thread_id: str | None = None,
) -> int:
    """Persist structured retrieval evidence."""
    if not evidence:
        return 0
    created_at = _now()
    rows = []
    for item in evidence:
        rows.append(
            (
                thread_id,
                query,
                str(item.get("evidence_id", "")),
                str(item.get("source_type", "")),
                str(item.get("source", "")),
                str(item.get("page", "")),
                item.get("score"),
                str(item.get("quote", "")),
                json.dumps(item.get("metadata", {}), ensure_ascii=False, default=str),
                created_at,
            )
        )

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO evidence_records
            (thread_id, query, evidence_id, source_type, source, page, score, quote, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def list_evidence_records(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent structured evidence records."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT thread_id, query, evidence_id, source_type, source, page, score, quote,
                   metadata_json, created_at
            FROM evidence_records
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    records = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        records.append(
            {
                "thread_id": row["thread_id"],
                "query": row["query"],
                "evidence_id": row["evidence_id"],
                "source_type": row["source_type"],
                "source": row["source"],
                "page": row["page"] or "",
                "score": row["score"],
                "quote": row["quote"],
                "metadata": metadata,
                "created_at": row["created_at"],
            }
        )
    return records


def save_paper_card(
    card: dict[str, Any],
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Persist one structured paper card and return the stored card."""
    created_at = _now()
    stored = {
        "card_id": str(card.get("card_id", "")),
        "thread_id": thread_id,
        "title": str(card.get("title", "")),
        "source": str(card.get("source", "")),
        "query": str(card.get("query", "")),
        "fields": card.get("fields", {}),
        "evidence": card.get("evidence", []),
        "created_at": created_at,
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cards
            (card_id, thread_id, title, source, query, fields_json, evidence_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored["card_id"],
                thread_id,
                stored["title"],
                stored["source"],
                stored["query"],
                json.dumps(stored["fields"], ensure_ascii=False, default=str),
                json.dumps(stored["evidence"], ensure_ascii=False, default=str),
                created_at,
            ),
        )
    return stored


def list_paper_cards(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent structured paper cards."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT card_id, thread_id, title, source, query, fields_json, evidence_json, created_at
            FROM paper_cards
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    cards = []
    for row in rows:
        try:
            fields = json.loads(row["fields_json"] or "{}")
        except json.JSONDecodeError:
            fields = {}
        try:
            evidence = json.loads(row["evidence_json"] or "[]")
        except json.JSONDecodeError:
            evidence = []
        cards.append(
            {
                "card_id": row["card_id"],
                "thread_id": row["thread_id"],
                "title": row["title"],
                "source": row["source"] or "",
                "query": row["query"],
                "fields": fields,
                "evidence": evidence,
                "created_at": row["created_at"],
            }
        )
    return cards


def save_citation_check(
    thread_id: str | None,
    report_id: str,
    claim_snippet: str,
    claimed_evidence_id: str | None,
    matched_evidence_id: str | None,
    status: str,
    similarity_score: float | None,
) -> None:
    """Persist one citation check result."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO citation_checks
            (thread_id, report_id, claim_snippet, claimed_evidence_id, matched_evidence_id,
             status, similarity_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                report_id,
                claim_snippet[:200],
                claimed_evidence_id,
                matched_evidence_id,
                status,
                similarity_score,
                _now(),
            ),
        )


def get_citation_verification(
    thread_id: str | None,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Return citation verification stats for one thread/report."""
    with _connect() as conn:
        if report_id:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS cnt
                FROM citation_checks
                WHERE thread_id = ? AND report_id = ?
                GROUP BY status
                """,
                (thread_id, report_id),
            ).fetchall()
            total_rows = conn.execute(
                "SELECT COUNT(*) FROM citation_checks WHERE thread_id = ? AND report_id = ?",
                (thread_id, report_id),
            ).fetchone()[0]
            details = conn.execute(
                """
                SELECT claim_snippet, claimed_evidence_id, matched_evidence_id, status, similarity_score
                FROM citation_checks
                WHERE thread_id = ? AND report_id = ?
                ORDER BY id
                """,
                (thread_id, report_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS cnt
                FROM citation_checks
                WHERE thread_id = ?
                GROUP BY status
                """,
                (thread_id,),
            ).fetchall()
            total_rows = conn.execute(
                "SELECT COUNT(*) FROM citation_checks WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]
            details = conn.execute(
                """
                SELECT claim_snippet, claimed_evidence_id, matched_evidence_id, status, similarity_score
                FROM citation_checks
                WHERE thread_id = ?
                ORDER BY id DESC
                LIMIT 100
                """,
                (thread_id,),
            ).fetchall()

    stats: dict[str, int] = {"total": total_rows}
    for row in rows:
        stats[row["status"]] = row["cnt"]

    detail_list = []
    for row in details:
        detail_list.append({
            "claim_snippet": row["claim_snippet"],
            "claimed_evidence_id": row["claimed_evidence_id"],
            "matched_evidence_id": row["matched_evidence_id"],
            "status": row["status"],
            "similarity_score": row["similarity_score"],
        })

    return {
        "stats": stats,
        "coverage_rate": round(
            (stats.get("verified", 0) + stats.get("low_confidence", 0))
            / max(stats["total"], 1),
            4,
        ),
        "unfounded_rate": round(
            stats.get("unfounded", 0) / max(stats["total"], 1), 4
        ),
        "details": detail_list,
    }


def set_session_db_path(path: str | Path) -> None:
    """Testing hook for isolated temporary databases."""
    global SESSION_DB_PATH
    SESSION_DB_PATH = Path(path)
    _initialized_paths.discard(SESSION_DB_PATH.resolve())
