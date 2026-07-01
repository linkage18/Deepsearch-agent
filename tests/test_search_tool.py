"""
Tests for the SearXNG search tool with mocked HTTP responses.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MockResponse:
    """Simulate a requests.Response object."""
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def mock_search_request(*args, **kwargs):
    """Return a mock SearXNG response with sample results."""
    return MockResponse(status_code=200, json_data={
        "results": [
            {
                "title": "Test Result 1",
                "url": "https://example.com/1",
                "content": "This is test content for result one",
                "engine": "google",
            },
            {
                "title": "Test Result 2",
                "url": "https://example.com/2",
                "content": "This is test content for result two",
                "engine": "duckduckgo",
            },
        ]
    })


def mock_empty_response(*args, **kwargs):
    return MockResponse(status_code=200, json_data={"results": []})


def mock_timeout_response(*args, **kwargs):
    import requests
    raise requests.exceptions.Timeout("Connection timed out")


def mock_connection_error(*args, **kwargs):
    import requests
    raise requests.exceptions.ConnectionError("Connection refused")


class TestInternetSearch:
    def test_search_returns_formatted_results(self):
        """Search with mocked results should return formatted string."""
        from app.tools.search_tool import internet_search

        with patch("requests.get", mock_search_request):
            result = internet_search.invoke({
                "query": "test query",
                "max_results": 5,
            })

        assert "[结果1]" in result
        assert "Test Result 1" in result
        assert "[结果2]" in result
        assert "Test Result 2" in result
        assert "example.com" in result

    def test_search_empty_results(self):
        """Empty results should return a helpful message."""
        from app.tools.search_tool import internet_search

        with patch("requests.get", mock_empty_response):
            result = internet_search.invoke({
                "query": "unique query that returns nothing",
                "max_results": 3,
            })

        assert "未搜索到" in result

    def test_search_timeout(self):
        """Timeout should return a timeout message."""
        from app.tools.search_tool import internet_search

        with patch("requests.get", mock_timeout_response):
            result = internet_search.invoke({
                "query": "timeout test",
                "max_results": 3,
            })

        assert "超时" in result

    def test_search_connection_error(self):
        """Connection error should return helpful message."""
        from app.tools.search_tool import internet_search

        with patch("requests.get", mock_connection_error):
            result = internet_search.invoke({
                "query": "connection test",
                "max_results": 3,
            })

        assert "无法连接" in result



class TestInternetSearchIntegration:
    """Integration-level tests for search tool behavior."""

    def test_topic_mapping(self):
        """Different topics should be handled without error."""
        from app.tools.search_tool import internet_search

        with patch("requests.get") as mock_get:
            mock_get.return_value = MockResponse(status_code=200, json_data={
                "results": [{
                    "title": "T", "url": "http://x.com",
                    "content": "test", "engine": "google",
                }]
            })
            result = internet_search.invoke({
                "query": "test", "topic": "news", "max_results": 3,
            })
            assert "T" in result

    def test_max_results_respected(self):
        """Tool should respect max_results parameter."""
        from app.tools.search_tool import internet_search

        with patch("requests.get") as mock_get:
            mock_get.return_value = MockResponse(status_code=200, json_data={
                "results": [
                    {"title": f"R{i}", "url": f"http://x.com/{i}",
                     "content": f"content{i}", "engine": "google"}
                    for i in range(10)
                ]
            })

            result = internet_search.invoke({
                "query": "test",
                "max_results": 3,
            })

            # Should only have 3 results
            assert result.count("[结果") == 3

    def test_include_raw_content(self):
        """When include_raw_content is True, raw_content should be preferred."""
        from app.tools.search_tool import internet_search

        with patch("requests.get") as mock_get:
            mock_get.return_value = MockResponse(status_code=200, json_data={
                "results": [{
                    "title": "Raw Test",
                    "url": "http://x.com/raw",
                    "content": "short snippet",
                    "raw_content": "very long raw content that should be used instead",
                    "engine": "google",
                }]
            })

            result = internet_search.invoke({
                "query": "test",
                "max_results": 5,
                "include_raw_content": True,
            })

            assert "very long raw content" in result

    def test_multiple_retries_on_failure(self, monkeypatch):
        """Tool should retry on transient failures."""
        monkeypatch.setenv("SEARXNG_MAX_RETRIES", "2")

        # Reimport after env change
        import importlib
        from app.tools import search_tool
        importlib.reload(search_tool)

        from app.tools.search_tool import internet_search

        call_count = 0

        def failing_then_succeeding(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                import requests
                raise requests.exceptions.Timeout("Timeout")
            return MockResponse(status_code=200, json_data={
                "results": [{
                    "title": "Retry Success",
                    "url": "http://x.com/success",
                    "content": "After retry",
                    "engine": "google",
                }]
            })

        with patch("requests.get", failing_then_succeeding):
            result = internet_search.invoke({
                "query": "retry test",
                "max_results": 3,
            })

        assert "Retry Success" in result
        assert call_count == 2


if __name__ == "__main__":
    pytest.main([__file__])
