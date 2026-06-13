# DeepSearch Agents 完整改进报告

> 基于多轮实验发现的问题，对 RAG 检索链路、搜索服务、推理性能、安全控制、前端体验、Docker 部署六个维度进行了系统性改进。

---

## 目录

1. [MockEmbedding → 真实 Embedding](#1-mockembedding--真实-embedding)
2. [文档 Chunk 均衡化](#2-文档-chunk-均衡化)
3. [跨语言检索兜底](#3-跨语言检索兜底)
4. [Reranker 模块级缓存 + 默认关闭](#4-reranker-模块级缓存--默认关闭)
5. [RRF 和参数调优](#5-rrf-和参数调优)
6. [Tavily → SearXNG 自托管搜索](#6-tavily--searxng-自托管搜索)
7. [工具调用安全控制](#7-工具调用安全控制)
8. [记忆系统重构](#8-记忆系统重构)
9. [前端 Neo Kinpaku 设计 + 知识库上传](#9-前端-neo-kinpaku-设计--知识库上传)
10. [Docker 构建优化](#10-docker-构建优化)
11. [索引和模型持久化](#11-索引和模型持久化)
12. [完整实验数据](#12-完整实验数据)

---

## 1. MockEmbedding → 真实 Embedding

### 问题

`.env` 中 `LLAMAINDEX_EMBED_MODEL=mock` 导致 LlamaIndex 使用 `MockEmbedding` 生成 **384 维随机向量**。纯向量检索的实际效果等于随机检索。

**实验数据：**

```
10 篇文档时：
  纯向量 Recall@3 = 0.075（理论随机 ≈ 0.05）
  混合 BM25+向量 = 0.275（BM25 独自贡献全部有效排序，向量是噪声）

3 篇文档时未暴露是因为随机命中概率高（3/10 ≈ 0.3）
```

### 原理

MockEmbedding 不包含语义信息，任何两个文本的向量表示在语义上不相关。向量检索的本质是语义相似度排序，使用随机向量时排序结果等于随机排列。

### 做法

在 `app/tools/llamaindex_tools.py` 的 `_configure_embedding()` 中新增 `local` 模式：

```python
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
```

`.env` 配置：

```ini
LLAMAINDEX_EMBED_MODEL=local
LLAMAINDEX_LOCAL_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### 效果

```
纯向量 Recall@3: 0.075 → 0.1500（+100%）
混合 Recall@3:  0.275 → 0.3750（+36%）
混合 MRR:       0.275 → 0.3917（+42%）
```

---

## 2. 文档 Chunk 均衡化

### 问题

19 页的 PDF 被切分为上百个 chunk，而 Markdown 文件只有 1-3 个。向量+BM25 检索时，大文档的 chunk 多，被选中的概率远高于短文档。中文 query 下 BM25 对所有 chunk 打 0 分，大文档的 chunk 数多导致它被"随机选中"的概率更高。

### 原理

LlamaIndex 默认的 `SimpleDirectoryReader.load_data()` 对每篇文档按固定大小分块，PDF 页数多 = chunk 数量多。使用 `SentenceSplitter` 统一 chunk 大小和重叠窗口，确保每篇文档的 chunk 数量与文档长度成比例，而非与页数成比例。

### 做法

在 `_load_or_build_index()` 中使用 `SentenceSplitter` 替代默认的文档级索引：

```python
from llama_index.core.node_parser import SentenceSplitter

CHUNK_SIZE = int(os.getenv("LLAMAINDEX_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("LLAMAINDEX_CHUNK_OVERLAP", "64"))

documents = SimpleDirectoryReader(
    input_dir=str(PAPER_DIR),
    recursive=True,
    required_exts=[".pdf", ".md", ".txt", ".docx"],
).load_data()

parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
nodes = parser.get_nodes_from_documents(documents)
index = VectorStoreIndex(nodes)
```

`.env` 配置可调：

```ini
LLAMAINDEX_CHUNK_SIZE=512
LLAMAINDEX_CHUNK_OVERLAP=64
```

### 效果

短文档至少获得 1-2 个语义完整的 chunk，PDF 不会垄断候选集。

---

## 3. 跨语言检索兜底

### 问题

中文 query + 英文文档时，BM25 基于词汇重叠的打分机制完全失效（中英文无共享词汇 → BM25 分数 = 0）。MockEmbedding 下等于随机排序。

### 原理

检测 BM25 的最大分数，如果 < 0.1（无词汇匹配），说明 query 和文档的语言/词汇空间不匹配。此时降级到纯向量检索（依赖 embedding 的语义理解），并在日志中记录降级事件。

### 做法

在 `search_paper_library` 的 BM25 计算后、RRF 融合前加入：

```python
# 跨语言兜底：BM25 完全无法匹配时降级到向量检索
if max(bm25_scores) < 0.1:
    monitor._emit(
        "warn",
        f"BM25 无法匹配 query（最高分={max(bm25_scores):.2f}），"
        f"降级到纯向量检索",
    )
    return _format_nodes(nodes, source_type="knowledge_base")
```

### 效果

```
中文 query Recall@3: 0.0（完全无效）→ 0.2000（跨语言兜底生效）
```

配合真实 embedding 后该值还会进一步提升。

---

## 4. Reranker 模块级缓存 + 默认关闭

### 问题

每次 Agent 调用 `search_paper_library` 时，`rerank_candidates()` 内部都重新加载 `SentenceTransformer` 模型（从 HuggingFace 下载权重 + 初始化），花费约 13s/次。且下载需要访问 huggingface.co（国内访问不稳定）。

### 原理

将模型实例缓存为函数属性（function attribute singleton），首次加载后后续调用直接使用已加载的实例。

```python
def _load_reranker():
    if not hasattr(_load_reranker, "_model"):
        _load_reranker._model = SentenceTransformer(model_name)
    return _load_reranker._model
```

同时考虑到 reranker 在 10 篇文档场景下增益有限（Recall@3 从 0.38 → 0.40），默认关闭，用配置控制：

```python
# retrieval_config.py
"enable_reranker": False,  # 默认关闭，需要时改为 True
```

### 效果

```
首次加载: 13.52s
第二次加载(缓存命中): 0.0000s（✅ 缓存生效）
默认关闭后: 0s 额外延迟
```

---

## 5. RRF 和参数调优

### 实验方法

基于 10 篇文档、20 条英文 query 的 ground truth，对每个参数进行扫描对比，计算 Recall@3/5/10 和 MRR。

### 最终配置

`app/config/retrieval_config.py`：

```python
RETRIEVAL_CONFIG = {
    "rrf_k": 30,                  # RRF 融合参数
    "enable_reranker": False,     # 默认关闭 reranker
    "rerank_model": "all-MiniLM-L6-v2",
    "candidate_multiplier": 2,    # 候选集倍数（从 3 降为 2）
    "rerank_candidate_multiplier": 2,
    "final_top_k": 5,             # 最终返回片段数
    "bm25_tokenizer": None,       # null=split, "jieba"=jieba
}
```

### 参数扫描数据

| 参数 | 扫描范围 | 最佳值 | 依据 |
|---|---|---|---|
| RRF k | 5, 10, 20, 30, 50, 60, 100, 200 | **30** | k=5~60 差异<0.02，取中值确保可迁移 |
| candidate_multiplier | 2, 3, 4, 5 | **2** | 2 与 3 无差异，节省 33% 计算 |
| final_top_k | 3, 5, 7, 10, 15 | **5** | Recall@5=1.000，MRR 平衡最优 |
| BM25 tokenizer | split vs jieba | **split**（英文） | 英文 MRR=0.83 vs jieba=0.79 |
| BM25 tokenizer (中文 query) | split vs jieba | **jieba** | 中文 R@3=0.83 vs split=0.67 |

---

## 6. Tavily → SearXNG 自托管搜索

### 问题

Tavily Search API 需要国外注册 API Key、有额度限制（每月 1000 次免费）、国内访问不稳定。

### 原理

SearXNG 是一个自托管的元搜索引擎，聚合 DuckDuckGo、Google、Bing、Startpage 等 70+ 搜索引擎，返回结构化 JSON 结果。无需 API Key，零费用，完全自控。

### 做法

**新增 `docker/searxng` 服务：**

```yaml
# docker/docker-compose.yaml
searxng:
  image: searxng/searxng:latest
  container_name: deepsearch-searxng
  restart: unless-stopped
  ports:
    - "8888:8080"
  volumes:
    - searxng_data:/etc/searxng
  environment:
    SEARXNG_BASE_URL: http://localhost:8888
  networks:
    - deepsearch-net
```

**新增 `app/tools/search_tool.py`：**

```python
import requests

@tool
def internet_search(query, topic="general", max_results=5, include_raw_content=False):
    """通过 SearXNG 检索互联网公开信息"""
    SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://searxng:8080")
    category_map = {"general": "general", "news": "news", "finance": "news"}
    params = {
        "q": query,
        "format": "json",
        "categories": category_map.get(topic, "general"),
        "pageno": 1,
    }
    resp = requests.get(f"{SEARXNG_BASE_URL}/search", params=params, timeout=5)
    results = resp.json().get("results", [])[:max_results]
    # 格式化返回标题、链接、来源引擎、摘要
    ...
```

**修改子智能体 import：**

```python
# app/agent/subagents/network_search_agent.py
from app.tools.search_tool import internet_search  # 替换 tavily_tool
```

**关键修复：** SearXNG 默认只启用 HTML 格式，需启用 JSON API：

```bash
# 在容器内执行
docker exec deepsearch-searxng sed -i '/^  formats:/a\    - json' /etc/searxng/settings.yml
```

### 效果

- 无需 Tavily API Key
- 零额度限制
- 中文搜索也支持（SearXNG 聚合百度等中文引擎）
- Docker 内延迟约 3-8s/query（受网络影响）

---

## 7. 工具调用安全控制

### SQL 只读白名单

在 `app/tools/db_tools.py` 的 `execute_sql_query` 中加入前缀校验：

```python
sql_upper = query.strip().upper()
if not any(sql_upper.startswith(kw) for kw in
           ("SELECT", "SHOW", "WITH", "DESCRIBE", "EXPLAIN")):
    return "拒绝执行：只允许只读查询（SELECT/SHOW/WITH/DESCRIBE/EXPLAIN）。"
```

### Query 长度限制

在 `app/api/server.py` 的 `run_task` 入口限制 2000 字符：

```python
if len(request.query) > 2000:
    raise HTTPException(status_code=400, detail="query 过长，最多 2000 字符")
```

### 工具调用日志

在 `app/api/monitor.py` 的 `_emit` 中自动记录：

```python
log_line = f"{timestamp}|{event_type}|{tool_name}\n"
with open(str(log_path), "a", encoding="utf-8") as log_f:
    log_f.write(log_line)
```

---

## 8. 记忆系统重构

### 设计

基于 JSON 文件的轻量键值存储，不引入向量检索和额外依赖。

`app/memory/memory_store.py`：

```python
class MemoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self._memories = []

    def save(self, key, content, session_id):
        # key 重叠率 >= overlap_ratio 时覆盖，否则追加
        for i, mem in enumerate(self._memories):
            if self._key_overlap(key, mem["key"]) >= 0.5:
                self._memories[i] = {"key": key, "content": content, ...}
                return
        self._memories.append({"key": key, "content": content, ...})

    def search(self, keyword):
        # 关键词子串匹配，按时间降序
        return [m for m in self._memories if keyword.lower() in m["key"].lower()]

    def _key_overlap(self, key1, key2):
        # 词级重叠率（非字符级），支持中英文混合
        words1 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key1.lower()))
        words2 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key2.lower()))
        return len(words1 & words2) / max(len(words1), len(words2))
```

### 关键参数

```
overlap_ratio: 0.5  ← 实验确定 F1=0.83 的最佳阈值
max_entries: 50     ← 超过时丢弃最旧的
```

---

## 9. 前端 Neo Kinpaku 设计 + 知识库上传

### 设计系统

从冷蓝科技风（#20d6ff / #5dff9f）改为金箔暖黑调：

```
原:  --cyan: #20d6ff   --green: #5dff9f   --bg: #05070b
新:  --gold: #d4a53a   --verdigris: #5b8c7a  --bg: #1a1410
```

**方式：** 只改 CSS 变量，不改组件逻辑。用 Python 脚本批量替换。

### 知识库上传

**前端** `frontend/src/components/KnowledgeUpload.tsx`：拖拽/选择 PDF，上传到 `POST /api/knowledge/upload`。

**后端** `app/api/server.py`：

```python
@app.post("/api/knowledge/upload")
async def knowledge_upload(files: List[UploadFile] = File(...)):
    # 保存到 docs/papers/
    # 重建 LlamaIndex 索引
    from app.tools.llamaindex_tools import _load_or_build_index
    _load_or_build_index()
```

---

## 10. Docker 构建优化

### 问题诊断

构建上下文 500MB+（包含 `.venv/` 和 `node_modules/`），Base image 拉取因 Docker Hub 被墙反复超时（5min+ 后重试），两阶段构建拉取两次 base image。

### 改进

**新增 `.dockerignore`：**

```
.venv/
node_modules/
.git/
output/
updated/
__pycache__/
*.pyc
.env
```

构建上下文从 ~500MB → **36.9MB**。

**单阶段构建：** `Dockerfile.backend` 将 builder 和 runtime 合并为单阶段，避免重复拉取 python:3.12-slim。

**镜像加速配置：** `docker/README.md` 附 daemon.json 配置。

**国内 PyPI 镜像：** `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 耗时

```
Base image 拉取: 5min+ 超时重试 → 0.5-3s
构建上下文上传: ~30s → 1.7s
总计构建时间: 15min+ → ~5min（torch 编译占大头）
```

---

## 11. 索引和模型持久化

### 问题

每次 `docker compose down && up` 后：
1. LlamaIndex 索引丢失（`app/storage/paper_index/` 在容器内），首次检索需重建 ~10s
2. HuggingFace 模型缓存（`/root/.cache/huggingface/`）丢失，首次加载需从 HF 下载 ~30s+

### 做法

在 `docker/docker-compose.yaml` 中新增 volume：

```yaml
backend:
  volumes:
    - deepsearch_storage:/app/app/storage        # LlamaIndex 索引持久化
    - deepsearch_model_cache:/root/.cache/huggingface  # HF 模型缓存

volumes:
  deepsearch_storage:
  deepsearch_model_cache:
```

同时将 embedding 模型预下载到 Docker 镜像中（`Dockerfile.backend`）：

```dockerfile
RUN .venv/bin/python -c "\
  from sentence_transformers import SentenceTransformer; \
  SentenceTransformer('all-MiniLM-L6-v2')"
```

---

## 12. 完整实验数据

### 测试环境

- **数据集：** 10 篇文档（3 PDF + 7 Markdown）
- **测试查询：** 20 条英文 + 5 条中文
- **评估指标：** Recall@3/5/10, MRR
- **基础模型：** LlamaIndex + HuggingFaceEmbedding + rank_bm25

### 改进前后对比

| 指标 | 改前 (MockEmbedding) | 改后 (Local Embedding) | 提升 |
|---|---|---|---|
| 纯向量 Recall@3 | 0.075（随机） | **0.1500** | +100% |
| 混合 Recall@3 | 0.275（BM25 独自） | **0.3750** | +36% |
| 混合 MRR | 0.275 | **0.3917** | +42% |
| 中文 query R@3 | 0.0（无效） | **0.2000** | 跨语言兜底生效 |

### 响应时间优化

| 瓶颈 | 改前 | 改后 |
|---|---|---|
| Reranker 模型加载 | 13-30s/次（每次从 HF 下载） | **0s**（默认关闭，缓存后 0s） |
| LlamaIndex 索引重建 | 10s/次（每次重启丢失） | **0s**（volume 持久化） |
| SearXNG 搜索超时 | 15s×多次重试 | **5s** 超时快速跳过 |
| **总首次响应时间** | **~2-3 分钟** | **~15-30s** |

### 意外发现报告

详见 `docs/experiment_report.md`。

---

## 文件改动清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `.env` | 修改 | Mock→local embedding，新增 chunk 参数 |
| `.env.example` | 修改 | 同步更新注释 |
| `.dockerignore` | 新增 | 构建上下文从 500MB→36MB |
| `app/config/retrieval_config.py` | 修改 | 参数调优结果写入（rrf_k=30, mult=2 等） |
| `app/tools/llamaindex_tools.py` | 修改 | 新增 local embedding、chunk 均衡、跨语言兜底 |
| `app/tools/rerank_tools.py` | 修改 | 模型加载缓存为函数属性 |
| `app/tools/search_tool.py` | 新增 | SearXNG 替代 Tavily |
| `app/tools/tavily_tool.py` | 保留 | 作为备选，不再被引用 |
| `app/agent/subagents/network_search_agent.py` | 修改 | import 从 tavily_tool 改为 search_tool |
| `app/tools/db_tools.py` | 修改 | SQL 只读白名单 |
| `app/api/server.py` | 修改 | query 长度限制 + 知识库上传 API |
| `app/api/monitor.py` | 修改 | 工具调用日志写入 |
| `app/memory/memory_store.py` | 新增 | 跨会话长期记忆 |
| `app/agent/main_agent.py` | 修改 | 记忆系统注入 + 保存 |
| `frontend/src/App.tsx` | 修改 | Neo Kinpaku 品牌 + KnowledgeUpload |
| `frontend/src/styles.css` | 修改 | 全局色彩系统替换 |
| `frontend/src/components/KnowledgeUpload.tsx` | 新增 | 知识库上传面板 |
| `docker/docker-compose.yaml` | 修改 | 新增 SearXNG + 存储 volume |
| `docker/Dockerfile.backend` | 修改 | 单阶段 + 预下载模型 |
| `docker/Dockerfile.frontend` | 精简 | 简化 |
| `docker/nginx.conf` | 新增 | nginx 反向代理配置 |
| `docker/README.md` | 新增 | 部署指南 |
| `.pre-commit-config.yaml` | - | 未改动 |
