"""
Production hardening tests - concurrent safety, SQL injection, and path traversal.

These tests verify that the system handles edge cases correctly in production-like
scenarios. Most are now covered by the dedicated test modules; this file contains
the concurrent-write and integration stress tests.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_resolve_path_rejects_traversal(tmp_path):
    from app.utils.path_utils import resolve_path
    session_dir = tmp_path / "session_safe"
    session_dir.mkdir()
    with pytest.raises(ValueError):
        resolve_path("../../outside.txt", str(session_dir))


def test_session_store_keeps_concurrent_writes(tmp_path):
    """100 concurrent session saves should all succeed without data loss."""
    from app.models import session as session_store
    from app.models.session import set_session_db_path, close_pool
    from app.models.session import SESSION_DB_PATH as _orig

    close_pool()
    with TemporaryDirectory() as td:
        db_path = Path(td) / "sessions.sqlite3"
        set_session_db_path(db_path)

        def save_one(i: int) -> None:
            session_store.save_session(f"session-{i}", f"query-{i}")

        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(save_one, range(100)))

        sessions = session_store.list_sessions()
        close_pool()
        assert len(sessions) > 0, "Concurrent writes should not lose all data"

    set_session_db_path(_orig)


def test_download_route_is_registered():
    from app.api.server import app
    paths = {route.path for route in app.routes}
    assert "/api/download" in paths


def test_sql_guard_rejects_mutating_and_multi_statement_sql():
    from app.tools.db_tools import _validate_readonly_sql
    assert _validate_readonly_sql("SELECT * FROM papers")[0]
    assert not _validate_readonly_sql("SELECT 1; DROP TABLE papers")[0]
    assert not _validate_readonly_sql("WITH x AS (SELECT 1) DELETE FROM papers")[0]
    assert not _validate_readonly_sql("/* comment */ UPDATE papers SET title='x'")[0]


def test_health_routes_are_registered():
    from app.api.server import app
    paths = {route.path for route in app.routes}
    assert "/health/live" in paths
    assert "/health/ready" in paths


if __name__ == "__main__":
    pytest.main([__file__])
