"""Tests for the ToolMonitor and ConnectionManager — event emission, WebSocket lifecycle."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestToolMonitor:
    def test_monitor_singleton(self):
        from app.api.monitor import ToolMonitor
        m1 = ToolMonitor()
        m2 = ToolMonitor()
        assert m1 is m2

    def test_report_tool_emits_event(self, monkeypatch):
        from app.api.monitor import monitor
        events = []
        monkeypatch.setattr(monitor, "_emit", lambda et, msg, data=None: events.append((et, msg, data)))
        monitor.report_tool("test_tool", {"key": "val"})
        assert len(events) == 1
        et, msg, data = events[0]
        assert et == "tool_start"
        assert "test_tool" in msg

    def test_report_assistant_emits_event(self, monkeypatch):
        from app.api.monitor import monitor
        events = []
        monkeypatch.setattr(monitor, "_emit", lambda et, msg, data=None: events.append((et, msg, data)))
        monitor.report_assistant("sub_agent", {"query": "q"})
        assert len(events) == 1

    def test_report_task_result(self, monkeypatch):
        from app.api.monitor import monitor
        events = []
        monkeypatch.setattr(monitor, "_emit", lambda et, msg, data=None: events.append((et, msg, data)))
        monitor.report_task_result("done")
        assert events[0][0] == "task_result"

    def test_report_task_cancelled(self, monkeypatch):
        from app.api.monitor import monitor
        events = []
        monkeypatch.setattr(monitor, "_emit", lambda et, msg, data=None: events.append((et, msg, data)))
        monitor.report_task_cancelled()
        assert events[0][0] == "task_cancelled"

    def test_report_session_dir(self, monkeypatch):
        from app.api.monitor import monitor
        events = []
        monkeypatch.setattr(monitor, "_emit", lambda et, msg, data=None: events.append((et, msg, data)))
        monitor.report_session_dir("/tmp/session_001")
        assert events[0][0] == "session_created"

    def test_set_websocket_manager(self):
        from app.api.monitor import ToolMonitor, ConnectionManager
        m = ToolMonitor()
        cm = ConnectionManager()
        m.set_websocket_manager(cm)
        assert m.websocket_manager is cm

    def test_emit_logs_to_file_on_tool_start(self, monkeypatch, tmp_path):
        from app.api.monitor import monitor
        monkeypatch.setattr("app.api.monitor.get_session_context", lambda: str(tmp_path))
        monkeypatch.setattr("app.api.monitor.get_thread_context", lambda: "test-001")
        monkeypatch.setattr(monitor, "_send_to_websocket", lambda *a, **kw: None)
        from app.models import session as s_mod
        monkeypatch.setattr(s_mod, "save_run_event", lambda *a, **kw: None)

        monitor._emit("tool_start", "test tool", {"tool_name": "demo_tool"})
        log = tmp_path / "tool_calls.log"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "tool_start" in content
        assert "demo_tool" in content


class TestConnectionManager:
    def test_set_loop(self):
        from app.api.monitor import ConnectionManager
        import asyncio
        cm = ConnectionManager()
        loop = asyncio.new_event_loop()
        cm.set_loop(loop)
        assert cm.loop is loop

    def test_disconnect_nonexistent(self):
        from app.api.monitor import ConnectionManager
        cm = ConnectionManager()
        # Calling disconnect with a nonexistent thread_id should not raise
        cm.disconnect("fake_ws", "nonexistent")
        assert "nonexistent" not in cm.active_connections

    def test_send_to_thread_no_active_passes(self):
        from app.api.monitor import ConnectionManager
        cm = ConnectionManager()
        import asyncio
        async def test():
            await cm.send_to_thread({"msg": "hello"}, "ghost")
        asyncio.run(test())

    def test_connect_and_disconnect(self):
        from app.api.monitor import ConnectionManager
        import asyncio
        from unittest.mock import AsyncMock

        cm = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()

        async def run():
            await cm.connect(mock_ws, "test-thread")
            assert "test-thread" in cm.active_connections
            cm.disconnect(mock_ws, "test-thread")
            assert "test-thread" not in cm.active_connections

        asyncio.run(run())
