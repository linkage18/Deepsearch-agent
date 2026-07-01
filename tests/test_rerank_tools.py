"""Tests for the reranking module — edge cases, empty inputs, error handling."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def prevent_model_load():
    """Prevent actual SentenceTransformer loading; patch with a deterministic stub."""
    import app.tools.rerank_tools as rt

    orig = rt._load_reranker
    rt._load_reranker = lambda: _DummyEncoder()
    yield
    rt._load_reranker = orig


class _DummyEncoder:
    """Deterministic encoder that returns 1D vector for string, 2D for list."""

    def encode(self, texts, normalize_embeddings=True):
        import numpy as np
        rng = np.random.RandomState(42)
        vec = rng.randn(384)
        if isinstance(texts, str):
            return vec
        return rng.randn(len(texts), 384)


class TestRerankCandidates:
    def test_empty_candidates(self):
        from app.tools.rerank_tools import rerank_candidates
        assert rerank_candidates("query", []) == []

    def test_single_candidate(self):
        from app.tools.rerank_tools import rerank_candidates
        candidates = [("text a", "source1.pdf", 0.5)]
        result = rerank_candidates("query", candidates, top_k=5)
        assert len(result) == 1
        assert result[0][1] == "source1.pdf"

    def test_top_k_limits_results(self):
        from app.tools.rerank_tools import rerank_candidates
        candidates = [(f"text{i}", f"s{i}.pdf", 0.5) for i in range(10)]
        result = rerank_candidates("query", candidates, top_k=3)
        assert len(result) == 3

    def test_top_k_defaults_to_all(self):
        from app.tools.rerank_tools import rerank_candidates
        candidates = [(f"text{i}", f"s{i}.pdf", 0.5) for i in range(5)]
        result = rerank_candidates("query", candidates, top_k=None)
        assert len(result) == 5

    def test_results_sorted_descending(self):
        from app.tools.rerank_tools import rerank_candidates
        candidates = [(f"text{i}", f"s{i}.pdf", float(i)) for i in range(5)]
        result = rerank_candidates("query", candidates, top_k=5)
        scores = [r[2] for r in result]
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))

    def test_preserves_text_and_source_in_output(self):
        from app.tools.rerank_tools import rerank_candidates
        candidates = [("hello world", "doc.pdf", 0.3)]
        result = rerank_candidates("test query", candidates)
        assert result[0][0] == "hello world"


class TestTokenize:
    def test_tokenize_jieba_missing_fallback(self, monkeypatch):
        import app.config.retrieval_config as rc
        monkeypatch.setitem(rc.RETRIEVAL_CONFIG, "bm25_tokenizer", "jieba")
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "jieba":
                raise ImportError
            return real_import(name, *args, **kwargs)

        builtins.__import__ = mock_import
        from app.tools.rerank_tools import _tokenize
        result = _tokenize("hello world test")
        builtins.__import__ = real_import
        assert result == ["hello", "world", "test"]

    def test_tokenize_default_split(self):
        from app.tools.rerank_tools import _tokenize
        result = _tokenize("hello world")
        assert result == ["hello", "world"]

    def test_tokenize_empty_string(self):
        from app.tools.rerank_tools import _tokenize
        assert _tokenize("") == []


class TestRerankSearchResultsTool:
    def test_invalid_json_returns_error(self):
        from app.tools.rerank_tools import rerank_search_results
        result = rerank_search_results.invoke({"query": "test", "candidates_json": "not-json", "top_k": 3})
        assert "失败" in result

    def test_empty_candidates_json(self):
        from app.tools.rerank_tools import rerank_search_results
        result = rerank_search_results.invoke({"query": "test", "candidates_json": "[]", "top_k": 3})
        assert "无有效" in result

    def test_valid_candidates_produces_output(self):
        from app.tools.rerank_tools import rerank_search_results
        candidates = [["text content", "source.pdf", 0.5]]
        result = rerank_search_results.invoke(
            {"query": "test", "candidates_json": json.dumps(candidates), "top_k": 5}
        )
        assert "结果1" in result
        assert "source.pdf" in result

    def test_top_k_honored(self):
        from app.tools.rerank_tools import rerank_search_results
        candidates = [[f"text{i}", f"s{i}.pdf", 0.5] for i in range(10)]
        result = rerank_search_results.invoke(
            {"query": "test", "candidates_json": json.dumps(candidates), "top_k": 2}
        )
        # "结果" is part of Chinese output encoding, count occurrences of source filenames
        assert sum(f"s{i}.pdf" in result for i in range(10)) == 2
