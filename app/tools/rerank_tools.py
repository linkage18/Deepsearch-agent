"""
轻量重排序工具模块

对 BM25+向量融合后的候选结果，用 cross-encoder 或 bi-encoder 做二次排序。
当前使用 sentence-transformers all-MiniLM-L6-v2 计算 query-doc 余弦相似度。
"""

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from langchain_core.tools import tool

from app.api.monitor import monitor
from app.config.retrieval_config import RETRIEVAL_CONFIG


def _load_reranker():
    """延迟加载 reranker 模型（模块级单例，避免重复加载）"""
    if not hasattr(_load_reranker, "_model"):
        from sentence_transformers import SentenceTransformer

        model_name = RETRIEVAL_CONFIG["rerank_model"]
        _load_reranker._model = SentenceTransformer(model_name)
        print(f"[Reranker] 已加载模型: {model_name}")
    return _load_reranker._model


def _tokenize(text: str) -> list[str]:
    """使用配置中的 tokenizer"""
    from app.config.retrieval_config import RETRIEVAL_CONFIG
    bm25_tokenizer = RETRIEVAL_CONFIG.get("bm25_tokenizer")
    if bm25_tokenizer == "jieba":
        try:
            import jieba
            return list(jieba.cut(text))
        except ImportError:
            pass
    return text.lower().split()


def rerank_candidates(
    query: str,
    candidates: list[tuple[str, str, float]],
    top_k: int | None = None,
) -> list[tuple[str, str, float]]:
    """
    对候选集做二次排序

    Args:
        query: 原始查询文本
        candidates: [(node_text, source_file, original_score), ...]
        top_k: 返回结果数，None 则返回全部

    Returns:
        按重排序分数降序排列的 [(node_text, source_file, rerank_score), ...]
    """
    if not candidates:
        return []

    if top_k is None:
        top_k = len(candidates)

    model = _load_reranker()
    texts = [c[0] for c in candidates]

    # 计算 query 与每个 candidate 的余弦相似度
    query_emb = model.encode(query, normalize_embeddings=True)
    doc_embs = model.encode(texts, normalize_embeddings=True)

    import numpy as np
    scores = np.dot(doc_embs, query_emb).tolist()

    # 按新分数降序排列
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda x: scores[x[0]], reverse=True)

    result = []
    for idx, (text, source, _) in indexed[:top_k]:
        result.append((text, source, scores[idx]))

    return result


@tool
def rerank_search_results(
    query: Annotated[str, "原始用户查询"],
    candidates_json: Annotated[str, "候选集 JSON 字符串，格式为 [['text','source',score], ...]"],
    top_k: Annotated[int, "返回结果数量，默认 5"] = 5,
) -> str:
    """
    对检索候选结果做二次重排序，返回排序后的文本块

    适用于向量检索或混合检索后有多个候选片段、需要按相关性精排的场景。
    :param query: 原始用户查询
    :param candidates_json: 候选片段 JSON
    :param top_k: 返回数量
    :return: 重排序后的格式化文本
    """
    import json

    monitor.report_tool(
        "检索结果重排序工具",
        {"query": query, "top_k": top_k},
    )

    try:
        candidates = json.loads(candidates_json)
        reranked = rerank_candidates(query, candidates, top_k)

        parts = []
        for i, (text, source, score) in enumerate(reranked, start=1):
            excerpt = " ".join(text.split())[:600]
            parts.append(
                f"[结果{i}] 来源:{source}; 重排序分数:{score:.4f}\n"
                f"片段:{excerpt}"
            )

        return "\n\n".join(parts) if parts else "无有效候选结果"
    except Exception as exc:
        return f"重排序失败: {str(exc)}"
