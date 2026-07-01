"""
Lightweight long-term memory store backed by SQLite with connection pooling.
"""

import queue
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.config.paths import SESSIONS_DB_PATH
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryStore:
    """Cross-session memory with durable SQLite writes and connection pooling."""

    _init_lock = threading.Lock()
    _initialized_paths: set[Path] = set()
    _pool: queue.Queue[sqlite3.Connection] | None = None
    _pool_lock = threading.Lock()
    POOL_SIZE = 4

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool or create one temporarily."""
        if MemoryStore._pool is None:
            with MemoryStore._pool_lock:
                if MemoryStore._pool is None:
                    MemoryStore._pool = queue.Queue(maxsize=self.POOL_SIZE)
                    for _ in range(self.POOL_SIZE):
                        conn = self._create_connection()
                        MemoryStore._pool.put(conn)

        try:
            conn = MemoryStore._pool.get_nowait()
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                conn.close()
        except queue.Empty:
            pass

        return self._create_connection()

    def _return_connection(self, conn: sqlite3.Connection) -> None:
        if MemoryStore._pool is None:
            conn.close()
            return
        try:
            MemoryStore._pool.put_nowait(conn)
        except queue.Full:
            conn.close()

    def _create_connection(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.path),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._init_db()
        conn = self._get_connection()
        try:
            yield conn
        finally:
            self._return_connection(conn)

    def _init_db(self) -> None:
        resolved = self.path.resolve()
        if resolved in self._initialized_paths:
            return
        with self._init_lock:
            if resolved in self._initialized_paths:
                return
            conn = self._create_connection()
            try:
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
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)"
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
        """Search memories by keyword (case-insensitive via SQLite LIKE)."""
        keyword_like = f"%{keyword}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, content, session_id, created_at, updated_at
                FROM memories
                WHERE key LIKE ? OR content LIKE ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT 20
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
                LIMIT 100
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        return cursor.rowcount > 0

    @classmethod
    def close_pool(cls) -> None:
        """Close all connections in the pool. Used by tests for cleanup."""
        pool = cls._pool
        cls._pool = None
        if pool is not None:
            while True:
                try:
                    conn = pool.get_nowait()
                    conn.close()
                except Exception:
                    break

    @staticmethod
    def _key_overlap(key1: str, key2: str) -> float:
        """Jaccard similarity on word tokens. Used for deduplication."""
        if not key1 or not key2:
            return 0.0
        words1 = set(re.findall(r"[a-zA-Z0-9_一-鿿]+", key1.lower()))
        words2 = set(re.findall(r"[a-zA-Z0-9_一-鿿]+", key2.lower()))
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / max(len(words1), len(words2))


memory_store = MemoryStore(SESSIONS_DB_PATH)
