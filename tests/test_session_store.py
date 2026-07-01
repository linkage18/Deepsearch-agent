"""
Comprehensive tests for the SQLite-backed session store.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def store():
    """Provide an isolated session store with proper cleanup."""
    from app.models import session as session_store
    from app.models.session import set_session_db_path, close_pool
    from app.models.session import SESSION_DB_PATH as _orig

    close_pool()
    with TemporaryDirectory() as td:
        db_path = Path(td) / "sessions.sqlite3"
        set_session_db_path(db_path)
        yield session_store
        close_pool()
        set_session_db_path(_orig)


class TestSessionCRUD:
    def test_save_and_get(self, store):
        store.save_session("session-1", "测试查询")
        session = store.get_session("session-1")
        assert session is not None
        assert session["title"].startswith("测试查询")
        assert not session["completed"]

    def test_get_nonexistent(self, store):
        assert store.get_session("nonexistent") is None

    def test_list_sessions_empty(self, store):
        assert store.list_sessions() == []

    def test_list_sessions_order(self, store):
        store.save_session("s1", "first")
        store.save_session("s2", "second")
        sessions = store.list_sessions()
        assert len(sessions) >= 2

    def test_double_save_ignored(self, store):
        store.save_session("dup", "first")
        store.save_session("dup", "second")
        session = store.get_session("dup")
        assert session["title"].startswith("first")

    def test_append_turn(self, store):
        store.save_session("turn-test", "测试")
        store.append_turn("turn-test", "问题1", "回答1")
        store.append_turn("turn-test", "问题2", "回答2")
        session = store.get_session("turn-test")
        assert len(session["turns"]) == 2
        assert session["turns"][0]["query"] == "问题1"

    def test_append_turn_to_nonexistent(self, store):
        store.append_turn("ghost", "q", "a")

    def test_update_session(self, store):
        store.save_session("upd", "测试")
        store.update_session("upd", completed=True, file_count=3)
        session = store.get_session("upd")
        assert session["completed"]
        assert session["file_count"] == 3

    def test_update_invalid_field_ignored(self, store):
        store.save_session("inv", "测试")
        store.update_session("inv", nonexistent_field="value")
        session = store.get_session("inv")
        assert session is not None

    def test_delete_session(self, store):
        store.save_session("del", "deleteme")
        assert store.delete_session("del")
        assert store.get_session("del") is None

    def test_delete_nonexistent(self, store):
        assert not store.delete_session("ghost")


class TestRunEvents:
    def test_save_and_list(self, store):
        store.save_run_event("thread-1", "tool_start", "测试事件", {"tool": "demo"})
        events = store.list_run_events("thread-1")
        assert len(events) == 1
        assert events[0]["event"] == "tool_start"
        assert events[0]["data"]["tool"] == "demo"

    def test_list_empty(self, store):
        assert store.list_run_events("nonexistent") == []

    def test_list_limit(self, store):
        for i in range(10):
            store.save_run_event("limit-test", "event", str(i))
        events = store.list_run_events("limit-test", limit=3)
        assert len(events) <= 3


class TestEvidenceRecords:
    def test_save_and_list(self, store):
        count = store.save_evidence_records(
            "react reasoning",
            [{
                "evidence_id": "kb-1",
                "source_type": "knowledge_base",
                "source": "react.pdf",
                "page": "3",
                "score": 0.82,
                "quote": "ReAct interleaves reasoning and acting.",
                "metadata": {"file_name": "react.pdf"},
            }],
        )
        assert count == 1
        records = store.list_evidence_records()
        assert len(records) == 1
        assert records[0]["source"] == "react.pdf"

    def test_save_empty(self, store):
        assert store.save_evidence_records("q", []) == 0

    def test_multiple_evidence(self, store):
        items = [
            {"evidence_id": f"kb-{i}", "source_type": "pdf", "source": f"doc{i}.pdf",
             "page": "", "score": 0.5, "quote": f"content{i}", "metadata": {}}
            for i in range(3)
        ]
        assert store.save_evidence_records("multi", items) == 3
        assert len(store.list_evidence_records()) == 3


class TestPaperCards:
    def test_save_and_list(self, store):
        card = store.save_paper_card({
            "card_id": "card-001",
            "title": "Test Paper",
            "source": "test.pdf",
            "query": "test method",
            "fields": {"method": ["GNN"]},
            "evidence": [{"text": "evidence"}],
        })
        assert card["card_id"] == "card-001"
        cards = store.list_paper_cards()
        assert len(cards) == 1

    def test_list_empty(self, store):
        assert store.list_paper_cards() == []


class TestCitationChecks:
    def test_save_and_get(self, store):
        store.save_citation_check("t", "r1", "claim text", "eid1", "match1", "verified", 0.85)
        result = store.get_citation_verification("t", "r1")
        assert result["stats"]["total"] == 1
        assert result["stats"]["verified"] == 1

    def test_get_without_report_id(self, store):
        store.save_citation_check("t", "r1", "c1", "e1", "m1", "verified", 0.9)
        store.save_citation_check("t", "r2", "c2", "e2", "m2", "unfounded", 0.1)
        result = store.get_citation_verification("t")
        assert result["stats"]["total"] == 2


if __name__ == "__main__":
    pytest.main([__file__])
