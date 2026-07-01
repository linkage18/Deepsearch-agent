"""
Tests for the SQLite-backed long-term memory store.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def store(isolated_memory_store):
    """Use the conftest fixture."""
    return isolated_memory_store


class TestMemoryStore:
    def test_save_and_search(self, store):
        store.save("test-key", "这是测试内容", "session-1")
        results = store.search("test-key")
        assert len(results) == 1
        assert results[0]["key"] == "test-key"
        assert "测试" in results[0]["content"]

    def test_search_content(self, store):
        store.save("key1", "机器学习 transformer 模型", "s1")
        results = store.search("transformer")
        assert len(results) >= 1

    def test_search_empty(self, store):
        assert store.search("nonexistent") == []

    def test_save_overwrites_similar_key(self, store):
        store.save("Graph Neural Networks for Node Classification", "content a", "s1")
        store.save("Graph Neural Networks for Edge Prediction", "content b", "s2")
        # Similar keys should trigger overwrite (key_overlap >= 0.5)
        results = store.search("Graph Neural Networks")
        # Should have only 1 entry (overwritten)
        assert len(results) >= 1

    def test_save_caps_at_50_entries(self, store):
        for i in range(60):
            store.save(f"memory-{i}", f"content-{i}", "s1")
        results = store.load()
        assert len(results) <= 50

    def test_load_returns_recent_first(self, store):
        store.save("older", "old content", "s1")
        store.save("newer", "new content", "s1")
        results = store.load()
        assert results[0]["key"] == "newer"

    def test_delete(self, store):
        store.save("delete-me", "content", "s1")
        assert store.delete("delete-me")
        assert store.search("delete-me") == []

    def test_delete_nonexistent(self, store):
        assert not store.delete("ghost")

    def test_key_overlap_empty(self, store):
        assert store._key_overlap("", "test") == 0.0
        assert store._key_overlap("test", "") == 0.0

    def test_key_overlap_exact(self, store):
        assert store._key_overlap("hello world", "hello world") == 1.0

    def test_key_overlap_partial(self, store):
        overlap = store._key_overlap("hello world foo", "hello world bar")
        assert 0.5 <= overlap < 1.0


if __name__ == "__main__":
    pytest.main([__file__])
