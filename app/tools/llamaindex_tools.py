"""
LlamaIndex 论文知识库工具模块

本模块面向论文研读场景提供本地论文库检索能力。
工具会从 LLAMAINDEX_PAPER_DIR 指向的目录读取 PDF、Markdown、TXT 等资料，
使用 LlamaIndex 建立可持久化索引，并返回带来源文件和片段编号的证据文本。
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Any

from dotenv import find_dotenv, load_dotenv
from langchain_core.tools import tool

from app.api.monitor import monitor

load_dotenv(find_dotenv())

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent


def _resolve_project_path(value: str | None, default: Path) -> Path:
    """把相对路径解析到项目根目录下，绝对路径保持原样。"""
    if not value:
        return default.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


PAPER_DIR = _resolve_project_path(
    os.getenv("LLAMAINDEX_PAPER_DIR"),
    PROJECT_ROOT / "docs" / "papers",
)
INDEX_DIR = _resolve_project_path(
    os.getenv("LLAMAINDEX_INDEX_DIR"),
    APP_ROOT / "storage" / "paper_index",
)
MANIFEST_PATH = INDEX_DIR / "_paper_manifest.json"
DEFAULT_TOP_K = int(os.getenv("LLAMAINDEX_SIMILARITY_TOP_K", "5"))


def _import_llama_index():
    """
    延迟导入 LlamaIndex，避免依赖尚未安装时后端启动直接失败。

    工具被真正调用时才需要 LlamaIndex；如果未安装，会返回清晰的安装提示。
    """
    try:
        from llama_index.core import (
            Settings,
            SimpleDirectoryReader,
            StorageContext,
            VectorStoreIndex,
            load_index_from_storage,
        )
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.node_parser import SentenceSplitter
    except ImportError as exc:
        raise RuntimeError(
            "未安装 LlamaIndex 依赖。请在项目根目录执行："
            "uv add llama-index llama-index-readers-file llama-index-embeddings-openai && uv sync"
        ) from exc

    return {
        "Settings": Settings,
        "SimpleDirectoryReader": SimpleDirectoryReader,
        "StorageContext": StorageContext,
        "VectorStoreIndex": VectorStoreIndex,
        "load_index_from_storage": load_index_from_storage,
        "MockEmbedding": MockEmbedding,
        "SentenceSplitter": SentenceSplitter,
    }


def _configure_embedding(imports: dict[str, Any]) -> None:
    """
    配置 LlamaIndex embedding。

    默认使用 MockEmbedding，保证没有额外 embedding key 时也能跑通流程。
    如果配置 LLAMAINDEX_EMBED_MODEL=openai，则尝试使用 OpenAI 兼容 embedding。
    """
    Settings = imports["Settings"]
    MockEmbedding = imports["MockEmbedding"]
    mode = os.getenv("LLAMAINDEX_EMBED_MODEL", "mock").lower()

    if mode == "openai":
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding

            Settings.embed_model = OpenAIEmbedding(
                model=os.getenv("LLAMAINDEX_OPENAI_EMBED_MODEL", "text-embedding-3-small"),
                api_key=os.getenv("OPENAI_API_KEY"),
                api_base=os.getenv("OPENAI_BASE_URL"),
            )
            return
        except Exception:
            pass

    if mode == "local":
        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            model_name = os.getenv(
                "LLAMAINDEX_LOCAL_EMBED_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            )
            Settings.embed_model = HuggingFaceEmbedding(model_name=model_name)
            print(f"[Embedding] 已加载本地模型: {model_name}")
            return
        except Exception as exc:
            print(f"[Embedding] 本地模型加载失败: {exc}，降级到 mock")

    Settings.embed_model = MockEmbedding(embed_dim=384)


def _supported_files() -> list[Path]:
    """返回论文库目录下可索引的文件。"""
    if not PAPER_DIR.exists():
        return []

    suffixes = {".pdf", ".md", ".txt", ".docx"}
    return sorted(
        path
        for path in PAPER_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _manifest() -> dict[str, Any]:
    """根据文件名、大小和修改时间生成索引清单，用于判断是否需要重建索引。"""
    files = _supported_files()
    entries = []
    for path in files:
        stat = path.stat()
        entries.append(
            {
                "path": str(path.relative_to(PAPER_DIR)).replace("\\", "/"),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )

    raw = json.dumps(entries, ensure_ascii=False, sort_keys=True)
    return {
        "digest": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "files": entries,
    }


def _load_saved_manifest() -> dict[str, Any] | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_manifest(value: dict[str, Any]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _index_is_current(current_manifest: dict[str, Any]) -> bool:
    if not INDEX_DIR.exists():
        return False
    saved = _load_saved_manifest()
    return bool(saved and saved.get("digest") == current_manifest.get("digest"))


def _load_or_build_index():
    """加载已有索引；论文库有变化时自动重建。"""
    imports = _import_llama_index()
    _configure_embedding(imports)

    SimpleDirectoryReader = imports["SimpleDirectoryReader"]
    StorageContext = imports["StorageContext"]
    VectorStoreIndex = imports["VectorStoreIndex"]
    load_index_from_storage = imports["load_index_from_storage"]

    current_manifest = _manifest()
    if not current_manifest["files"]:
        raise RuntimeError(
            f"论文库目录为空或不存在：{PAPER_DIR}。请把论文 PDF、Markdown 或 TXT 放入该目录。"
        )

    if _index_is_current(current_manifest):
        storage_context = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
        return load_index_from_storage(storage_context)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    SentenceSplitter = imports["SentenceSplitter"]
    documents = SimpleDirectoryReader(
        input_dir=str(PAPER_DIR),
        recursive=True,
        required_exts=[".pdf", ".md", ".txt", ".docx"],
    ).load_data()

    # 统一 chunk 大小，避免大文档（PDF 19页）垄断召回
    CHUNK_SIZE = int(os.getenv("LLAMAINDEX_CHUNK_SIZE", "512"))
    CHUNK_OVERLAP = int(os.getenv("LLAMAINDEX_CHUNK_OVERLAP", "64"))
    parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = parser.get_nodes_from_documents(documents)
    index = VectorStoreIndex(nodes)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    _save_manifest(current_manifest)
    return index


def _format_nodes(
    nodes: list[Any],
    source_type: str = "knowledge_base",
) -> str:
    if not nodes:
        return "未从论文知识库中召回相关片段。"

    parts = []
    for index, node_with_score in enumerate(nodes, start=1):
        node = getattr(node_with_score, "node", node_with_score)
        score = getattr(node_with_score, "score", None)
        metadata = getattr(node, "metadata", {}) or {}
        source = (
            metadata.get("file_name")
            or metadata.get("file_path")
            or metadata.get("document_title")
            or "未知来源"
        )
        page = metadata.get("page_label") or metadata.get("page_number") or ""
        text = getattr(node, "text", "") or node.get_content()
        excerpt = " ".join(text.split())[:900]
        score_text = f"{score:.4f}" if isinstance(score, int | float) else "N/A"
        page_text = f"; 页码:{page}" if page else ""
        parts.append(
            f"[证据{index}] 来源:{source}{page_text}; 相似度:{score_text}; "
            f"来源类型:{source_type}\n"
            f"片段:{excerpt}"
        )
    return "\n\n".join(parts)


@tool
def list_paper_library_files() -> str:
    """
    列出当前 LlamaIndex 论文库中的可索引文件。

    当需要了解本地论文库有哪些论文、笔记或综述材料时调用。
    :return: 论文库文件列表，或目录为空的提示
    """
    monitor.report_tool("LlamaIndex论文库文件列表工具：list_paper_library_files")

    files = _supported_files()
    if not files:
        return f"论文库目录为空或不存在：{PAPER_DIR}"

    lines = [f"论文库目录：{PAPER_DIR}", "可用文件："]
    lines.extend(f"- {path.relative_to(PAPER_DIR)}" for path in files)
    return "\n".join(lines)


@tool
def search_paper_library(
    query: Annotated[str, "论文库检索问题，例如某个方法、实验设置或研究主题"],
    top_k: Annotated[int, "返回证据片段数量，默认 5，建议 3 到 8"] = DEFAULT_TOP_K,
) -> str:
    """
    从 LlamaIndex 本地论文库中检索相关原文片段。

    内部使用混合检索策略：向量召回候选 -> BM25 RRF 融合 -> MiniLM 重排序。
    适合查询论文方法、实验设置、结论、局限性和相关工作。返回结果会保留来源文件、
    页码元数据和片段内容，供主智能体生成综述时引用。
    :param query: 检索问题
    :param top_k: 召回片段数量
    :return: 格式化后的证据片段列表
    """
    from app.config.retrieval_config import RETRIEVAL_CONFIG

    monitor.report_tool(
        "LlamaIndex论文库检索工具：search_paper_library",
        {"query": query, "top_k": top_k},
    )

    try:
        index = _load_or_build_index()
        cfg = RETRIEVAL_CONFIG
        candidate_k = max(1, min(int(top_k) * cfg["candidate_multiplier"], 20))
        retriever = index.as_retriever(similarity_top_k=candidate_k)
        nodes = retriever.retrieve(query)

        if not nodes:
            return "未从论文知识库中召回相关片段。"

        # ----- Step 1: BM25 RRF 融合 -----
        texts = []
        for n in nodes:
            node = getattr(n, "node", n)
            t = getattr(node, "text", "") or node.get_content()
            texts.append(t)

        # 使用配置中的 tokenizer
        bm25_tokenizer = cfg.get("bm25_tokenizer")
        if bm25_tokenizer == "jieba":
            import jieba
            tokenize_fn = lambda x: list(jieba.cut(x))
        else:
            tokenize_fn = lambda x: x.lower().split()

        tokenized_corpus = [tokenize_fn(t) for t in texts]
        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = tokenize_fn(query)
        bm25_scores = bm25.get_scores(tokenized_query)

        # 跨语言兜底：BM25 完全无法匹配时降级到向量检索
        if max(bm25_scores) < 0.1:
            monitor._emit(
                "warn",
                f"BM25 无法匹配 query（最高分={max(bm25_scores):.2f}），"
                f"降级到纯向量检索",
            )
            return _format_nodes(nodes, source_type="knowledge_base")

        k = cfg["rrf_k"]
        fused = []
        for i, n in enumerate(nodes):
            vector_rank = i + 1
            bm25_rank_args = sorted(
                range(len(bm25_scores)), key=lambda j: bm25_scores[j], reverse=True
            )
            try:
                bm25_rank = bm25_rank_args.index(i) + 1
            except ValueError:
                bm25_rank = len(nodes)
            rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)
            fused.append((n, rrf_score))

        fused.sort(key=lambda x: x[1], reverse=True)
        fused_nodes = [fn[0] for fn in fused[:max(1, min(int(top_k), len(fused)))]]

        # ----- Step 2: MiniLM 重排序（可选，默认关闭以加快首次响应） -----
        if cfg.get("enable_reranker", False):
            try:
                from app.tools.rerank_tools import rerank_candidates

                candidate_texts = []
                for n in fused_nodes:
                    node = getattr(n, "node", n)
                    t = getattr(node, "text", "") or node.get_content()
                    meta = getattr(node, "metadata", {}) or {}
                    source = (
                        meta.get("file_name")
                        or meta.get("file_path")
                        or meta.get("document_title")
                        or "未知来源"
                    )
                    score = getattr(n, "score", 0.0) or 0.0
                    candidate_texts.append((t, source, score))

                reranked = rerank_candidates(query, candidate_texts, top_k=int(top_k))
                reranked_nodes = []
                for text, source, r_score in reranked:
                    for n in fused_nodes:
                        node = getattr(n, "node", n)
                        nt = getattr(node, "text", "") or node.get_content()
                        if nt == text:
                            n.score = r_score
                            reranked_nodes.append(n)
                            break
                    else:
                        reranked_nodes.append(n)
                final_nodes = reranked_nodes
            except Exception:
                final_nodes = fused_nodes
        else:
            final_nodes = fused_nodes

        return _format_nodes(final_nodes, source_type="knowledge_base")
    except Exception as exc:
        return f"LlamaIndex 论文库检索失败：{str(exc)}"


@tool
def retrieve_paper_evidence(
    claim_or_question: Annotated[str, "需要查找证据支持的结论或问题"],
    paper_title: Annotated[str, "可选，限定某篇论文标题或关键词"] = "",
    top_k: Annotated[int, "返回证据片段数量，默认 5"] = DEFAULT_TOP_K,
) -> str:
    """
    围绕某个结论或问题检索证据片段。

    如果 paper_title 非空，会把标题加入检索条件，优先召回该论文相关片段。
    :param claim_or_question: 待核验证据的结论或问题
    :param paper_title: 可选论文标题或关键词
    :param top_k: 召回片段数量
    :return: 证据片段列表
    """
    query = (
        f"论文标题或关键词：{paper_title}\n需要核验的结论或问题：{claim_or_question}"
        if paper_title
        else claim_or_question
    )
    monitor.report_tool(
        "LlamaIndex论文证据检索工具：retrieve_paper_evidence",
        {"claim_or_question": claim_or_question, "paper_title": paper_title, "top_k": top_k},
    )

    try:
        index = _load_or_build_index()
        retriever = index.as_retriever(similarity_top_k=max(1, min(int(top_k), 10)))
        nodes = retriever.retrieve(query)
        return _format_nodes(nodes)
    except Exception as exc:
        return f"LlamaIndex 论文证据检索失败：{str(exc)}"


@tool
def build_paper_card(
    paper_title: Annotated[str, "论文标题或能定位论文的关键词"],
) -> str:
    """
    为某篇论文召回可用于生成论文卡片的证据材料。

    本工具不直接替模型写最终卡片，而是返回围绕研究问题、方法、实验、结论、
    局限性的证据片段。子智能体应基于返回证据整理结构化论文卡片。
    :param paper_title: 论文标题或关键词
    :return: 论文卡片证据材料
    """
    monitor.report_tool(
        "LlamaIndex论文卡片证据工具：build_paper_card",
        {"paper_title": paper_title},
    )

    query = (
        f"{paper_title} research problem method experiment datasets conclusion limitations"
    )
    try:
        index = _load_or_build_index()
        retriever = index.as_retriever(similarity_top_k=8)
        nodes = retriever.retrieve(query)
        evidence = _format_nodes(nodes)
        return (
            "请基于以下证据整理论文卡片，字段包括：标题、研究问题、核心方法、"
            "实验设置、主要结论、局限性、来源片段。\n\n"
            f"{evidence}"
        )
    except Exception as exc:
        return f"LlamaIndex 论文卡片证据召回失败：{str(exc)}"
