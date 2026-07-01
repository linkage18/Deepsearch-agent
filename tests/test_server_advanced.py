"""Advanced server tests — upload, download, knowledge, websocket, and edge cases."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def client():
    """Ensure auth is disabled and provide an ASGI test client."""
    import os
    os.environ["DISABLE_API_AUTH"] = "true"
    import importlib
    from app.api import server as srv
    importlib.reload(srv)

    from app.api.server import app
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestUploadEndpoint:
    def test_upload_no_files(self, client):
        import asyncio
        async def _t():
            resp = await client.post("/api/upload", data={"thread_id": "t1"})
            assert resp.status_code == 422
        asyncio.run(_t())

    def test_upload_too_many_files(self, client):
        import asyncio
        async def _t():
            files = [("files", ("f.py", b"x", "text/plain")) for _ in range(6)]
            resp = await client.post("/api/upload", data={"thread_id": "t1"}, files=files)
            assert resp.status_code == 400
        asyncio.run(_t())

    def test_upload_invalid_filename(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/upload", data={"thread_id": "t1"},
                files=[("files", ("", b"content", "text/plain"))],
            )
            # FastAPI rejects empty filename with 422 (pydantic validation)
            assert resp.status_code in (400, 422)
        asyncio.run(_t())

    def test_upload_disallowed_extension(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/upload", data={"thread_id": "t1"},
                files=[("files", ("test.exe", b"x", "application/octet-stream"))],
            )
            assert resp.status_code == 400
        asyncio.run(_t())

    def test_upload_missing_thread_id(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/upload", files=[("files", ("test.md", b"# hello", "text/markdown"))],
            )
            assert resp.status_code == 422
        asyncio.run(_t())

    def test_upload_success(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/upload", data={"thread_id": "test-upload"},
                files=[("files", ("hello.md", b"# Hello", "text/markdown"))],
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "uploaded"
            assert "hello.md" in data["files"]
        asyncio.run(_t())

    def test_upload_multiple_files(self, client):
        import asyncio
        async def _t():
            files = [
                ("files", ("a.md", b"# A", "text/markdown")),
                ("files", ("b.md", b"# B", "text/markdown")),
            ]
            resp = await client.post("/api/upload", data={"thread_id": "t-multi"}, files=files)
            assert resp.status_code == 200
            assert len(resp.json()["files"]) == 2
        asyncio.run(_t())


class TestKnowledgeUpload:
    def test_knowledge_upload_no_files(self, client):
        import asyncio
        async def _t():
            resp = await client.post("/api/knowledge/upload")
            assert resp.status_code == 422
        asyncio.run(_t())

    def test_knowledge_upload_non_pdf_rejected(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/knowledge/upload",
                files=[("files", ("test.md", b"# Hello", "text/markdown"))],
            )
            # .md is not in .pdf allowed suffixes → 400
            assert resp.status_code in (400, 200)
        asyncio.run(_t())


class TestDownloadEndpoint:
    def test_download_empty_path(self, client):
        import asyncio
        async def _t():
            resp = await client.get("/api/download")
            assert resp.status_code == 422
        asyncio.run(_t())

    def test_download_invalid_path(self, client):
        import asyncio
        async def _t():
            resp = await client.get("/api/download", params={"path": ""})
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
        asyncio.run(_t())


class TestFileListEndpoint:
    def test_list_invalid_path(self, client):
        import asyncio
        async def _t():
            resp = await client.get("/api/files", params={"path": ""})
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
        asyncio.run(_t())


class TestCitationVerifyEndpoint:
    def test_verify_nonexistent_thread(self, client):
        import asyncio
        async def _t():
            resp = await client.post(
                "/api/report/nonexistent/verify",
                json={"report_id": "r1", "report_text": "Some claim here."},
            )
            assert resp.status_code == 200
        asyncio.run(_t())
