import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from app.api import server
from app.api.context import reset_session_context, set_session_context, set_thread_context
from app.api.monitor import monitor
from app.models import session as session_store
from app.tools.db_tools import _validate_readonly_sql
from app.utils.path_utils import resolve_path


def test_resolve_path_rejects_traversal(tmp_path):
    session_dir = tmp_path / "session_safe"
    session_dir.mkdir()

    with pytest.raises(ValueError):
        resolve_path("../../outside.txt", str(session_dir))


def test_session_store_keeps_concurrent_writes(tmp_path):
    session_store.set_session_db_path(tmp_path / "sessions.sqlite3")

    def save_one(i: int) -> None:
        session_store.save_session(f"session-{i}", f"query-{i}")

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(save_one, range(100)))

    assert len(session_store.list_sessions()) == 100


def test_download_route_is_registered():
    paths = {route.path for route in server.app.routes}
    assert "/api/download" in paths


def test_upload_rejects_path_traversal_filename(tmp_path):
    original_updated_dir = server.updated_dir
    server.updated_dir = tmp_path

    async def run_request():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/upload",
                data={"thread_id": "safe-session"},
                files={"files": ("../escape.pdf", b"pdf", "application/pdf")},
            )

    try:
        response = asyncio.run(run_request())
    finally:
        server.updated_dir = original_updated_dir

    assert response.status_code == 200
    assert not (tmp_path / "escape.pdf").exists()
    assert (tmp_path / "session_safe-session" / "escape.pdf").exists()


def test_sql_guard_rejects_mutating_and_multi_statement_sql():
    assert _validate_readonly_sql("SELECT * FROM papers")[0]
    assert not _validate_readonly_sql("SELECT 1; DROP TABLE papers")[0]
    assert not _validate_readonly_sql("WITH x AS (SELECT 1) DELETE FROM papers")[0]
    assert not _validate_readonly_sql("/* comment */ UPDATE papers SET title='x'")[0]


def test_monitor_events_are_persisted(tmp_path):
    session_store.set_session_db_path(tmp_path / "sessions.sqlite3")
    session_token = set_session_context(str(tmp_path))
    thread_token = set_thread_context("thread-events")
    try:
        monitor._emit("tool_start", "测试事件", {"tool_name": "demo"})
    finally:
        reset_session_context(session_token, thread_token)

    events = session_store.list_run_events("thread-events")
    assert len(events) == 1
    assert events[0]["event"] == "tool_start"
    assert events[0]["data"]["tool_name"] == "demo"


def test_evidence_records_are_persisted(tmp_path):
    session_store.set_session_db_path(tmp_path / "sessions.sqlite3")

    count = session_store.save_evidence_records(
        "react reasoning",
        [
            {
                "evidence_id": "kb-1",
                "source_type": "knowledge_base",
                "source": "react.pdf",
                "page": "3",
                "score": 0.82,
                "quote": "ReAct interleaves reasoning and acting.",
                "metadata": {"file_name": "react.pdf"},
            }
        ],
    )

    records = session_store.list_evidence_records()
    assert count == 1
    assert len(records) == 1
    assert records[0]["source"] == "react.pdf"
    assert records[0]["metadata"]["file_name"] == "react.pdf"


def test_health_routes_are_registered():
    paths = {route.path for route in server.app.routes}
    assert "/health/live" in paths
    assert "/health/ready" in paths
