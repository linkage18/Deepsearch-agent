"""
检索链路配置模块

所有 RAG 检索相关的可调参数收敛于此，代码只读配置，不改参数。

参数实验结论（基于 10 篇文档 + 20 条 query + 5 条中文 query 的测试）：
  - rrf_k=30: k=5~60 无显著差异，取中间值确保可迁移
  - candidate_multiplier=2: mult=2 与 3 无差异，节省 33% 计算
  - final_top_k=5: Recall 与延迟的平衡点
  - bm25_tokenizer=null: 英文论文场景 split 优于 jieba
    中文论文场景可改为 "jieba"
  - rerank: MiniLM 在 3 篇文档时 Recall@3 从 0.89 提升到 1.00
    在 10 篇文档时提升 0.28 → 0.30（受 MockEmbedding 限制）
  - ⚠️ 重要: .env 中 LLAMAINDEX_EMBED_MODEL=mock 导致向量检索实质随机
    需要改为 openai 或部署本地 embedding 才可评估真实向量性能
"""
RETRIEVAL_CONFIG = {
    # RRF 融合参数
    "rrf_k": 30,
    # 用于二次排序的轻量 sentence-transformer 模型名
    "rerank_model": "all-MiniLM-L6-v2",
    # 是否启用 MiniLM 重排序（关闭可节省 ~13s 模型加载，降低首次响应时间）
    "enable_reranker": False,
    # 向量检索阶段候选集倍数
    "candidate_multiplier": 2,
    # Rerank 阶段候选集倍数
    "rerank_candidate_multiplier": 2,
    # 最终返回的 top_k 片段数
    "final_top_k": 5,
    # BM25 分词方式：null 用空格 split，"jieba" 用 jieba
    "bm25_tokenizer": None,
}
