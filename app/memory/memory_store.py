"""
Lightweight long-term memory store backed by SQLite.
"""

import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.config.paths import SESSIONS_DB_PATH


class MemoryStore:
    """Cross-session memory with durable SQLite writes."""

    _init_lock = threading.Lock()
    _initialized_paths: set[Path] = set()

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._init_db()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        resolved = self.path.resolve()
        if resolved in self._initialized_paths:
            return
        with self._init_lock:
            if resolved in self._initialized_paths:
                return
            conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT NOT NULL,
                        content TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                self._initialized_paths.add(resolved)
            finally:
                conn.close()

    def save(self, key: str, content: str, session_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM memories").fetchall()
            for row in rows:
                if self._key_overlap(key, row["key"]) >= 0.5:
                    conn.execute(
                        """
                        UPDATE memories
                        SET key = ?, content = ?, session_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (key, content, session_id, now, row["id"]),
                    )
                    conn.execute("COMMIT")
                    return

            conn.execute(
                """
                INSERT INTO memories (key, content, session_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, content, session_id, now),
            )
            conn.execute(
                """
                DELETE FROM memories
                WHERE id NOT IN (
                    SELECT id FROM memories
                    ORDER BY COALESCE(updated_at, created_at) DESC
                    LIMIT 50
                )
                """
            )
            conn.execute("COMMIT")

    def search(self, keyword: str) -> list[dict]:
        keyword_like = f"%{keyword.lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, content, session_id, created_at, updated_at
                FROM memories
                WHERE lower(key) LIKE ? OR lower(content) LIKE ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                """,
                (keyword_like, keyword_like),
            ).fetchall()
        return [dict(row) for row in rows]

    def load(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, content, session_id, created_at, updated_at
                FROM memories
                ORDER BY COALESCE(updated_at, created_at) DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        return cursor.rowcount > 0

    @staticmethod
    def _key_overlap(key1: str, key2: str) -> float:
        if not key1 or not key2:
            return 0.0
        words1 = set(re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", key1.lower()))
        words2 = set(re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", key2.lower()))
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / max(len(words1), len(words2))


memory_store = MemoryStore(SESSIONS_DB_PATH)
