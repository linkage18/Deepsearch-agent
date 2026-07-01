"""Tests for the Tavily internet search tool — mocking the client at module level."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def patch_tavily(monkeypatch):
    """Mock the tavily module and client before tests run."""

    class FakeTavilyClient:
        def search(self, query="", topic="general", max_results=5, include_raw_content=False):
            return {
                "query": query,
                "results": [
                    {"title": "Result 1", "url": "https://example.com/1", "content": "Sample"},
                    {"title": "Result 2", "url": "https://example.com/2", "content": "More"},
                ],
                "answer": None,
            }

    import types
    fake = types.ModuleType("tavily")
    fake.TavilyClient = lambda api_key="": FakeTavilyClient()
    monkeypatch.setitem(sys.modules, "tavily", fake)
    yield


class TestInternetSearch:
    def test_basic_search(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "test query", "max_results": 5})
        assert result["query"] == "test query"
        assert len(result["results"]) == 2

    def test_search_with_topic(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "news", "topic": "news", "max_results": 3})
        assert isinstance(result, dict)
        assert "results" in result

    def test_search_with_raw_content(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "test", "include_raw_content": True})
        assert isinstance(result, dict)

    def test_search_empty_query(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "", "max_results": 5})
        assert result["query"] == ""

    def test_search_minimal_params(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "hello"})
        assert len(result["results"]) == 2

    def test_search_result_structure(self):
        from app.tools.tavily_tool import internet_search
        result = internet_search.invoke({"query": "test"})
        r = result["results"][0]
        assert "title" in r
        assert "url" in r
        assert "content" in r
