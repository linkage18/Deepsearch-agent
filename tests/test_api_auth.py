"""
Tests for API authentication and security middleware.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _restore_server_module():
    """Restore server module to conftest defaults after auth state tests."""
    import os
    import importlib
    from app.api import server
    os.environ["DISABLE_API_AUTH"] = "true"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "100"
    os.environ.pop("API_KEY", None)
    importlib.reload(server)


@pytest.fixture(scope="module", autouse=True)
def auth_test_cleanup():
    yield
    _restore_server_module()


class TestApiAuth:
    def test_health_live_public(self):
        """Health endpoints should be accessible without auth."""
        from app.api.server import app
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

        async def _test():
            resp = await client.get("/health/live")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

        import asyncio
        asyncio.run(_test())

    def test_health_ready_public(self):
        """Ready endpoint should be accessible without auth."""
        from app.api.server import app
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

        async def _test():
            resp = await client.get("/health/ready")
            assert resp.status_code == 200

        import asyncio
        asyncio.run(_test())

    def test_api_key_rejected_when_enabled(self, monkeypatch):
        """When auth is enabled, requests without API key should be rejected."""
        monkeypatch.setenv("DISABLE_API_AUTH", "false")
        monkeypatch.setenv("API_KEY", "test-key-123")

        import importlib
        from app.api import server
        importlib.reload(server)

        from app.api.server import app
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

        async def _test():
            resp = await client.post(
                "/api/task",
                json={"query": "test", "thread_id": "test-auth"},
            )
            assert resp.status_code == 401

            resp2 = await client.post(
                "/api/task",
                json={"query": "test", "thread_id": "test-auth-2"},
                headers={"X-API-Key": "test-key-123"},
            )
            assert resp2.status_code != 401

        import asyncio
        asyncio.run(_test())

    def test_api_key_rejected_wrong_key(self, monkeypatch):
        """Wrong API key should be rejected."""
        monkeypatch.setenv("DISABLE_API_AUTH", "false")
        monkeypatch.setenv("API_KEY", "real-key")

        import importlib
        from app.api import server
        importlib.reload(server)

        from app.api.server import app
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

        async def _test():
            resp = await client.post(
                "/api/task",
                json={"query": "test"},
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

        import asyncio
        asyncio.run(_test())


class TestRateLimiting:
    def test_rate_limit_exceeded(self, monkeypatch):
        """Rate limiter should block requests after threshold."""
        monkeypatch.setenv("DISABLE_API_AUTH", "false")
        monkeypatch.setenv("API_KEY", "test-key")
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")

        import importlib
        from app.api import server
        importlib.reload(server)

        from app.api.server import app
        from httpx import ASGITransport, AsyncClient

        server._request_counts.clear()

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")

        async def _test():
            headers = {"X-API-Key": "test-key"}
            for _ in range(5):
                resp = await client.get("/health/live", headers=headers)
                assert resp.status_code == 200

            resp = await client.get("/health/live", headers=headers)
            assert resp.status_code == 429

        import asyncio
        asyncio.run(_test())


if __name__ == "__main__":
    pytest.main([__file__])
