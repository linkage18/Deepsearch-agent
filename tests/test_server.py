"""
Integration tests for the FastAPI server endpoints.

Note: These tests run against the ASGI transport without Docker dependencies.
Endpoints requiring MySQL or SearXNG will fail gracefully in test mode.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client():
    """Provide an async HTTP client against the FastAPI app."""
    from app.api.server import app
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestHealthEndpoints:
    def test_live(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/health/live")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        asyncio.run(_test())

    def test_ready(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert "status" in data
            assert "checks" in data
        asyncio.run(_test())


class TestTaskEndpoints:
    def test_submit_task_empty_query_valid(self, client):
        import asyncio
        async def _test():
            resp = await client.post("/api/task", json={"query": "", "thread_id": "test-empty"})
            # Empty query passes length check (only > 2000 is rejected)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "started"

        asyncio.run(_test())

    def test_submit_task_short_query(self, client):
        import asyncio
        async def _test():
            resp = await client.post(
                "/api/task",
                json={"query": "test hello", "thread_id": "test-task-001"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "started"
            assert data["thread_id"]
        asyncio.run(_test())

    def test_submit_task_long_query_rejected(self, client):
        import asyncio
        async def _test():
            resp = await client.post(
                "/api/task",
                json={"query": "x" * 2001, "thread_id": "test-long"},
            )
            assert resp.status_code == 400
        asyncio.run(_test())

    def test_cancel_nonexistent_task(self, client):
        import asyncio
        async def _test():
            resp = await client.post("/api/task/nonexistent/cancel")
            assert resp.status_code == 404
        asyncio.run(_test())

    def test_get_task_events_empty(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/task/nonexistent/events")
            assert resp.status_code == 200
            data = resp.json()
            assert data["events"] == []
        asyncio.run(_test())


class TestSessionEndpoints:
    def test_list_sessions(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/sessions")
            assert resp.status_code == 200
            data = resp.json()
            assert "sessions" in data
        asyncio.run(_test())

    def test_get_nonexistent_session(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/sessions/nonexistent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["session"] is None
        asyncio.run(_test())

    def test_delete_nonexistent_session(self, client):
        import asyncio
        async def _test():
            resp = await client.delete("/api/sessions/nonexistent")
            assert resp.status_code == 200
            data = resp.json()
            assert not data["deleted"]
        asyncio.run(_test())


class TestFileEndpoints:
    def test_download_without_path(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/download", params={"path": "/nonexistent"})
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
        asyncio.run(_test())

    def test_download_path_traversal_rejected(self, client):
        import asyncio
        async def _test():
            resp = await client.get(
                "/api/download",
                params={"path": "/etc/passwd"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "拒绝" in data.get("error", "")
        asyncio.run(_test())

    def test_list_files_outside_output_rejected(self, client):
        import asyncio
        async def _test():
            resp = await client.get(
                "/api/files",
                params={"path": "/etc"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "拒绝" in data.get("error", "")
        asyncio.run(_test())


class TestEvidenceEndpoints:
    def test_list_evidence(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/evidence", params={"limit": 10})
            assert resp.status_code == 200
            data = resp.json()
            assert "evidence" in data
        asyncio.run(_test())

    def test_list_evidence_caps_limit(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/evidence", params={"limit": 9999})
            assert resp.status_code == 200
        asyncio.run(_test())


class TestPaperCardEndpoints:
    def test_build_empty_title(self, client):
        import asyncio
        async def _test():
            resp = await client.post(
                "/api/paper-cards/build",
                json={"title": ""},
            )
            assert resp.status_code == 400
        asyncio.run(_test())

    def test_list_paper_cards(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/paper-cards")
            assert resp.status_code == 200
        asyncio.run(_test())

    def test_paper_matrix(self, client):
        import asyncio
        async def _test():
            resp = await client.get("/api/paper-matrix")
            assert resp.status_code == 200
        asyncio.run(_test())


class TestReviewAndCitationEndpoints:
    def test_review_report_missing_topic(self, client):
        import asyncio
        async def _test():
            resp = await client.post(
                "/api/review-report",
                json={"topic": ""},
            )
            # Should work with empty topic (uses default)
            assert resp.status_code == 200
        asyncio.run(_test())

    def test_verification_no_report(self, client):
        import asyncio
        async def _test():
            resp = await client.get(
                "/api/report/nonexistent/verification",
                params={"report_id": "r1"},
            )
            assert resp.status_code == 200
        asyncio.run(_test())


if __name__ == "__main__":
    pytest.main([__file__])
