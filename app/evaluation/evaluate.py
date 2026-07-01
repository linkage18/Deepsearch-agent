"""
RAG 评测脚本

对 _ground_truth.json 中的每条 query，分别运行三种检索策略：
1. 纯向量
2. 混合（BM25 + 向量 RRF 融合）
3. 全链路（混合 + MiniLM 重排序）

输出 Recall@K 和 MRR 对比表格。

用法：uv run python -m app.evaluation.evaluate
"""

import json
import os
import sys
import time
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["PYTHONWARNINGS"] = "ignore"

GT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "papers", "_ground_truth.json"
)

RETRIEVAL_CONFIG: dict[str, Any] = {}
RECALL_KS = [3, 5, 10]


def _load_config() -> dict[str, Any]:
    """从 retrieval_config 获取当前参数，确保评测与线上链路一致。"""
    from app.config.retrieval_config import RETRIEVAL_CONFIG as cfg
    return dict(cfg)


def _get_tokenize_fn():
    """根据配置获取分词函数，避免重复代码。"""
    bm25_tok = RETRIEVAL_CONFIG.get("bm25_tokenizer")
    if bm25_tok == "jieba":
        import jieba
        return lambda x: list(jieba.cut(x))
    return lambda x: x.lower().split()


def _retrieve_and_hybrid(query: str, top_k: int) -> tuple[list[Any], list[str]]:
    """执行向量检索 + BM25 RRF 融合，返回 (nodes, sources)。"""
    from app.tools.llamaindex_tools import _load_or_build_index
    from rank_bm25 import BM25Okapi

    index = _load_or_build_index()
    candidate_k = max(1, min(top_k * 3, 20))
    retriever = index.as_retriever(similarity_top_k=candidate_k)
    nodes = retriever.retrieve(query)

    if not nodes:
        return [], []

    texts = []
    for n in nodes:
        node = getattr(n, "node", n)
        t = getattr(node, "text", "") or node.get_content()
        texts.append(t)

    tokenize_fn = _get_tokenize_fn()
    tokenized_corpus = [tokenize_fn(t) for t in texts]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(tokenize_fn(query))

    # BM25 退化兜底
    if max(bm25_scores) < 0.1:
        sources = _nodes_to_sources(nodes)
        return nodes[:top_k], sources[:top_k]

    k = RETRIEVAL_CONFIG.get("rrf_k", 60)
    bm25_rank_args = sorted(
        range(len(bm25_scores)), key=lambda j: bm25_scores[j], reverse=True
    )

    fused = []
    for i, n in enumerate(nodes):
        vector_rank = i + 1
        try:
            bm25_rank = bm25_rank_args.index(i) + 1
        except ValueError:
            bm25_rank = len(nodes)
        rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)
        fused.append((n, rrf_score))

    fused.sort(key=lambda x: x[1], reverse=True)
    fused_nodes = [fn[0] for fn in fused[:top_k]]
    sources = _nodes_to_sources(fused_nodes)
    return fused_nodes, sources


def _nodes_to_sources(nodes: list[Any]) -> list[str]:
    """从节点列表中提取来源文件名。"""
    sources = []
    for n in nodes:
        node = getattr(n, "node", n)
        meta = getattr(node, "metadata", {}) or {}
        source = (
            meta.get("file_name")
            or meta.get("file_path")
            or meta.get("document_title")
            or "未知"
        )
        sources.append(source)
    return sources


def load_ground_truth() -> list[dict]:
    with open(GT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_vector_only(query: str, top_k: int) -> list[str]:
    """纯向量检索。"""
    from app.tools.llamaindex_tools import _load_or_build_index

    try:
        index = _load_or_build_index()
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)
        return _nodes_to_sources(nodes)
    except Exception as exc:
        print(f"  [Error] 纯向量检索失败: {exc}")
        return []


def run_hybrid(query: str, top_k: int) -> list[str]:
    """混合检索（向量 + BM25 RRF）。"""
    try:
        _, sources = _retrieve_and_hybrid(query, top_k)
        return sources
    except Exception as exc:
        print(f"  [Error] 混合检索失败: {exc}")
        return []


def run_full_pipeline(query: str, top_k: int) -> list[str]:
    """全链路（混合 + MiniLM 重排序）。"""
    from app.tools.rerank_tools import rerank_candidates

    try:
        nodes, _ = _retrieve_and_hybrid(query, top_k * 2)

        candidate_texts = []
        for n in nodes:
            node = getattr(n, "node", n)
            t = getattr(node, "text", "") or node.get_content()
            meta = getattr(node, "metadata", {}) or {}
            source = (
                meta.get("file_name")
                or meta.get("file_path")
                or meta.get("document_title")
                or "未知"
            )
            score = getattr(n, "score", 0.0) or 0.0
            candidate_texts.append((t, source, score))

        reranked = rerank_candidates(query, candidate_texts, top_k=top_k)
        return [s for _, s, _ in reranked]
    except Exception as exc:
        print(f"  [Error] 全链路检索失败: {exc}")
        return []


def compute_metrics(
    results: list[list[str]], ground_truths: list[list[str]], ks: list[int]
) -> dict:
    """计算 Recall@K 和 MRR。"""
    metrics = {}
    for k in ks:
        recalls = []
        reciprocal_ranks = []
        for pred_sources, gt_docs in zip(results, ground_truths):
            top_k = pred_sources[:k]
            hits = sum(1 for gt in gt_docs if any(gt in s for s in top_k))
            recalls.append(hits / max(len(gt_docs), 1))
            for rank, source in enumerate(top_k, 1):
                if any(gt in source for gt in gt_docs):
                    reciprocal_ranks.append(1.0 / rank)
                    break
            else:
                reciprocal_ranks.append(0.0)

        metrics[k] = {
            "recall": sum(recalls) / max(len(recalls), 1),
            "mrr": sum(reciprocal_ranks) / max(len(reciprocal_ranks), 1),
        }
    return metrics


def print_table(results: dict[str, dict], ks: list[int], fmt: str = "text"):
    """打印对比表格。"""
    if fmt == "markdown":
        header = "| " + "Strategy" + "".join(
            [f" | Recall@{str(k)}" for k in ks] + [" | MRR |"]
        )
        sep = "| " + "---" + "".join([" | ---" for _ in ks] + [" | --- |"])
        print(header)
        print(sep)
        for strategy, metrics in results.items():
            row = f"| {strategy}"
            for k in ks:
                row += f" | {metrics[k]['recall']:.4f}"
            row += f" | {metrics[ks[0]]['mrr']:.4f} |"
            print(row)
    else:
        header = f"{'Strategy':<20}" + "".join(
            [f" | {'Recall@'+str(k):<10}" for k in ks]
            + [f" | {'MRR':<10}"]
        )
        sep = "-" * len(header)
        print(header)
        print(sep)
        for strategy, metrics in results.items():
            row = f"{strategy:<20}"
            for k in ks:
                row += f" | {metrics[k]['recall']:<10.4f}"
            row += f" | {metrics[ks[0]]['mrr']:<10.4f}"
            print(row)
        print(sep)


def main():
    import argparse

    global RETRIEVAL_CONFIG
    RETRIEVAL_CONFIG = _load_config()

    parser = argparse.ArgumentParser(description="RAG 检索策略评测")
    parser.add_argument(
        "--format", choices=["text", "md", "markdown"], default="text",
        help="输出格式：text（终端表格）或 md / markdown（Markdown 表格）",
    )
    args = parser.parse_args()
    output_fmt = "markdown" if args.format in ("md", "markdown") else "text"

    ks = RECALL_KS

    if output_fmt == "text":
        print("=" * 60)
        print("RAG 检索策略评测")
        print(f"配置: rrf_k={RETRIEVAL_CONFIG.get('rrf_k')}, "
              f"rerank={RETRIEVAL_CONFIG.get('rerank_model')}, "
              f"multiplier={RETRIEVAL_CONFIG.get('candidate_multiplier')}")
        print("=" * 60)

    ground_truth = load_ground_truth()
    queries = [g["query"] for g in ground_truth]
    gt_docs = [g["doc_ids"] for g in ground_truth]

    print(f"\n评测集: {len(queries)} 条 query")
    for i, q in enumerate(queries):
        print(f"  [{i+1}] {q[:60]}... -> {len(gt_docs[i])} doc(s)")

    strategies: dict[str, Callable] = {
        "纯向量": run_vector_only,
        "混合(BM25+向量)": run_hybrid,
        "全链路(+rerank)": run_full_pipeline,
    }

    all_results = {}
    for name, func in strategies.items():
        print(f"\n--- 运行: {name} ---")
        t0 = time.time()
        all_sources = []
        for i, q in enumerate(queries):
            print(f"  [{i+1}/{len(queries)}] 检索中...", end=" ")
            sys.stdout.flush()
            sources = func(q, max(ks))
            all_sources.append(sources)
            print(f"召回 {len(sources)} 个片段")

        metrics = compute_metrics(all_sources, gt_docs, ks)
        all_results[name] = metrics
        elapsed = time.time() - t0
        print(f"  耗时: {elapsed:.1f}s")

    if output_fmt == "markdown":
        print("\n")
    else:
        print("\n\n" + "=" * 60)
        print("评测结果")
        print("=" * 60)
    print_table(all_results, ks, fmt=output_fmt)

    print("\n推荐配置:")
    best_strategy = max(
        all_results.keys(),
        key=lambda s: (
            all_results[s][3]["mrr"] if 3 in all_results[s] else 0,
            all_results[s][3]["recall"] if 3 in all_results[s] else 0,
        ),
    )
    best_mrr = all_results[best_strategy][3]["mrr"]
    best_r3 = all_results[best_strategy][3]["recall"]
    best_r5 = all_results[best_strategy][5]["recall"]
    print(
        f"  策略: {best_strategy} "
        f"(MRR={best_mrr:.4f}, Recall@3={best_r3:.4f}, Recall@5={best_r5:.4f})"
    )


if __name__ == "__main__":
    main()
