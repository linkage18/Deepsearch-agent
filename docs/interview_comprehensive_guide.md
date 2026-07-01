# 科研文献证据管理与综述生成系统 — 面试完整指南

---

## 目录

1. [项目全景设计](#1-项目全景设计)
2. [技术架构详解](#2-技术架构详解)
3. [100 道面试题](#3-100-道面试题)
   - [八股基础（25 题）](#31-八股基础)
   - [项目设计（25 题）](#32-项目设计)
   - [场景题（25 题）](#33-场景题)
   - [HR 综合（25 题）](#34-hr-综合)
4. [改进思路与落地](#4-改进思路与落地)
5. [测试过程与结果](#5-测试过程与结果)
6. [项目设计困难与取舍](#6-项目设计困难与取舍)
7. [简历 Hook 地图](#7-简历-hook-地图)
8. [系统架构分类总览](#8-系统架构分类总览)
   - [8.1 智能体编排层](#81-智能体编排层-agent-orchestration)
   - [8.2 检索与排序层](#82-检索与排序层-retrieval--ranking)
   - [8.3 数据持久化层](#83-数据持久化层-data-persistence)
   - [8.4 API 与实时通信层](#84-api-与实时通信层-api--realtime)
   - [8.5 安全防护层](#85-安全防护层-security)
   - [8.6 证据处理与报告生成](#86-证据处理与报告生成-evidence--reports)
   - [8.7 测试与评测体系](#87-测试与评测体系-testing--evaluation)
   - [8.8 部署与配置层](#88-部署与配置层-deployment--config)

---

## 1. 项目全景设计

### 1.1 项目定位

面向个人科研用户的**多智能体文献调研与综述生成系统**。解决三大痛点：

- **文献检索分散**：公开网页、学术论文元数据、本地 PDF 全文分布在多个入口
- **综述写作效率低**：从散乱笔记到结构化综述缺乏中间沉淀
- **引用追溯困难**：写综述时找不到原始证据来源、页码

### 1.2 简历描述（4 条核心产出）

| # | 标题 | 一句话 |
|---|------|--------|
| 1 | 多源检索 Agent 流程 + 可观测机制 | 基于 DeepAgents+LangGraph 设计 Orchestrator-Workers 架构，拆分三条工具链路，WebSocket 实时推送 + SQLite WAL 持久化，支持断线重连 |
| 2 | 多策略检索与融合排序流水线 | LlamaIndex 向量 + BM25 + RRF 融合 + MiniLM 重排序，建立 34 条 ground-truth (8 主题簇 × 3 难度) 做三维 A/B 对比，混合 BM25+RRF MRR 0.97 |
| 3 | 证据结构化沉淀模块 | 证据记录 → 论文卡片 → 对比矩阵 → Markdown 综述初稿，形成完整闭环 |
| 4 | 工程化质量保障与安全防护 | API Key 鉴权、四层 SQL 注入防护、文件三层校验、ContextVar 会话隔离、255 项测试、三种 embedding 模式、可插拔策略配置 |

### 1.3 核心流程

```
用户提交查询
    ↓
主智能体 (DeepAgents + LangGraph) 任务规划
    ├── 网络搜索子智能体 (SearXNG) → 公开资料
    ├── 论文知识子智能体 (LlamaIndex) → 本地论文库
    └── 数据库查询子智能体 (MySQL) → 论文元数据
    ↓
多源结果融合 (BM25 + 向量检索 + RRF 排序)
    ↓
MiniLM 重排序 (eval 链路启用，生产按需)
    ↓
证据结构化沉淀
    ├── 证据记录 (EvidenceRecord) → 含来源、页码、原文片段、分数
    ├── 论文卡片 (PaperCard) → 按字段分类 (problem/method/experiment...)
    ├── 对比矩阵 (PaperMatrix) → 多论文横向比较
    └── 综述初稿 (Markdown) → 自动生成带引用标注的综述报告
    ↓
WebSocket 实时推送 (进度、工具调用、结果)
    ↓
引用校验 (citation_checker) → 验证声明与证据匹配度
```

### 1.4 技术栈

| 层次 | 技术 |
|------|------|
| AI 框架 | DeepAgents 0.5.7, LangGraph 1.1.10 |
| RAG 检索 | LlamaIndex 0.12+, BM25, RRF, Sentence-Transformers (all-MiniLM-L6-v2) |
| 后端 | Python 3.12, FastAPI, asyncio, WebSocket |
| 数据库 | SQLite WAL (会话/证据/事件日志), MySQL 8.4 (论文元数据) |
| 搜索 | SearXNG (自建元搜索引擎) |
| 部署 | Docker, Docker Compose, Nginx 反向代理 |
| 测试 | pytest, httpx.ASGITransport, coverage.py, monkeypatch |

---

## 2. 技术架构详解

### 2.1 多智能体协作架构

```
┌─────────────────────────────────────────────────────────┐
│                   DeepAgents 框架                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │           主智能体 (main_agent)                   │   │
│  │  - 任务规划与拆解                                 │   │
│  │  - 子智能体调度                                  │   │
│  │  - 结果汇总与综述生成                             │   │
│  └────────────┬──────────────┬──────────────┬───────┘   │
│               │              │              │           │
│    ┌──────────▼──┐  ┌───────▼───────┐  ┌──▼──────────┐ │
│    │ 网络搜索     │  │ 论文知识库    │  │ 数据库查询   │ │
│    │ 子智能体     │  │ 子智能体      │  │ 子智能体     │ │
│    │ SearXNG/     │  │ LlamaIndex    │  │ MySQL        │ │
│    │ Tavily       │  │ BM25+向量     │  │              │ │
│    └─────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 2.2 检索与排序管线

```
用户查询
    ↓
LlamaIndex 检索
    ├── 向量检索 (embedding cosine similarity, candidate_multiplier=2)
    ├── BM25 关键词检索 (jieba / split tokenizer)
    └── RRF 融合 (Reciprocal Rank Fusion, k=30, 零参数)
    ↓
候选片段 (candidate_k = top_k × 2, 最大 20)
    ↓
MiniLM 重排序 (cross-encoder, 仅 eval 链路启用, 默认关闭)
    ↓
Top-K 最终结果 (final_top_k=5)
```

> **注意**：4 层流水线（含 MiniLM 重排序）在 eval 脚本中才完整使用。生产搜索链路默认只做 3 层（向量 + BM25 + RRF），因为 MiniLM 加载耗时 ~13s 且实测在 90 篇论文的评测中重排序反而降低了 Recall（全链路 MRR 0.87 vs 混合 MRR 0.97）。

### 2.3 后端 API 架构

```
FastAPI App
    ├── Middleware
    │   ├── CORSMiddleware
    │   ├── API Key Auth (verify_api_key)
    │   └── Rate Limiting (per-IP, 60/min)
    │
    ├── Health
    │   ├── GET /health/live
    │   └── GET /health/ready (含 SQLite/MySQL/SearXNG 检查)
    │
    ├── Task
    │   ├── POST /api/task → 提交异步 Agent 任务
    │   ├── POST /api/task/{id}/cancel
    │   └── GET /api/task/{id}/events
    │
    ├── Evidence & Paper Cards
    │   ├── GET /api/evidence
    │   ├── POST /api/paper-cards/build
    │   ├── GET /api/paper-cards
    │   ├── GET /api/paper-matrix
    │   └── POST /api/review-report
    │
    ├── Citation
    │   ├── POST /api/report/{id}/verify
    │   └── GET /api/report/{id}/verification
    │
    ├── Files
    │   ├── POST /api/upload (会话附件)
    │   ├── POST /api/knowledge/upload (论文入库)
    │   ├── GET /api/download
    │   └── GET /api/files
    │
    ├── Sessions
    │   ├── GET /api/sessions
    │   ├── GET /api/sessions/{id}
    │   └── DELETE /api/sessions/{id}
    │
    └── WebSocket
        └── WS /ws/{thread_id} → 实时进度推送
```

### 2.4 数据模型

```
Session (会话)
  ├── id, title, query_preview, turns_json
  ├── file_count, completed, created_at, updated_at
  └── RunEvent (运行事件)
       └── thread_id, event_type, message, data_json

EvidenceRecord (证据记录)
  ├── query, evidence_id, source_type, source
  ├── page, score, quote, metadata_json
  └── created_at

PaperCard (论文卡片)
  ├── card_id, title, source, query
  ├── fields_json (problem/method/experiment/conclusion/limitation)
  ├── evidence_json
  └── created_at

CitationCheck (引用校验)
  ├── thread_id, report_id
  ├── claim_snippet, claimed_evidence_id
  ├── matched_evidence_id, status, similarity_score
  └── created_at
```

---

## 3. 100 道面试题

### 3.1 八股基础（25 题）

#### Python

**Q1: Python 中 `__new__` 和 `__init__` 的区别？项目哪里用到了？**

> `__new__` 是类方法，负责创建实例（分配内存）；`__init__` 是实例方法，负责初始化。`__new__` 先于 `__init__` 执行。
>
> 项目中 `ToolMonitor` 用 `__new__` 实现了单例模式（`app/api/monitor.py:30-34`）：
> ```python
> def __new__(cls):
>     if cls._instance is None:
>         cls._instance = super().__new__(cls)
>     return cls._instance
> ```

**Q2: `asyncio.run()` 与 `loop.run_until_complete()` 的区别？**

> `asyncio.run()` 是 Python 3.7+ 的高层 API，自动创建新事件循环、运行协程、关闭循环。`loop.run_until_complete()` 需要手动管理循环生命周期。项目中测试用例使用了 `asyncio.run(_test())`，而在 WebSocket 管理器中使用 `loop.create_task()` 和 `asyncio.run_coroutine_threadsafe()` 实现跨线程协程投递。

**Q3: Python 中 GIL 的影响？项目如何处理并发？**

> GIL 限制同一进程同时只能执行一个 Python 线程。项目使用 `asyncio` 协程实现 I/O 密集型并发（FastAPI 请求处理、WebSocket 推送），而非多线程。对于 Agent 任务，使用 `asyncio.Semaphore` 控制最大并发数（默认 4），避免资源耗尽。

**Q4: `importlib.reload` 的作用和风险？项目遇到了什么问题？**

> `reload` 重新执行模块代码，更新 `sys.modules` 中的模块对象。风险：已有对象引用旧模块的类/函数，不会自动更新；模块级状态会重置。项目中 auth 测试使用 `reload` 后未恢复状态，导致后续 20 个 server 测试全部失败。

**Q5: 项目中的 WebSocket 断线重连机制是如何实现的？**

> `ConnectionManager` 以 `thread_id → WebSocket` 的字典维护连接。断线时 `WebSocketDisconnect` 触发 `manager.disconnect()` 清理连接，但 Agent 任务继续在后台运行。
> 
> 重连机制：页面刷新后前端重新建立 WebSocket 连接，调用 `GET /api/task/{id}/events` 拉取该 thread_id 的历史事件（从 SQLite `run_events` 表读取），然后继续监听实时推送。核心思路是"事件持久化 + 拉取补全"——WebSocket 负责实时，SQLite 负责历史。
> 
> 代码位置：`app/api/monitor.py` 的 `ConnectionManager.connect/disconnect/send_to_thread`，加上 `app/api/server.py` 的 `GET /api/task/{id}/events` 端点。

**Q6: 三种 embedding 模式（mock/local/openai）的设计意图是什么？**

> 为了降低部署和调试的门槛：
> - **mock**：随机向量，用于测试流水线能否跑通，不需要下载任何模型
> - **local**：本地 `sentence-transformers/all-MiniLM-L6-v2`，384 维，适合离线/私有化场景
> - **openai**：调用 OpenAI Embedding API（如 text-embedding-3-large），3072 维，效果最好但需要 API Key 和网络
> 
> 通过 `RETRIEVAL_CONFIG["embed_mode"]` 切换，无需改代码。架构上使用策略模式（Strategy Pattern）——`get_embedding_model()` 根据配置返回对应实现。

**Q7: 什么是装饰器？项目哪里使用了装饰器？**

> 装饰器是高阶函数，接受函数/类作为参数并返回增强版本。项目中使用 `@tool` 装饰器（LangChain）将普通函数暴露为智能体可调用的工具，使用 `@app.post/get` 装饰器定义 FastAPI 路由，使用 `@asynccontextmanager` 定义异步上下文管理器（lifespan）。

**Q8: 生成器与协程的关系？**

> 生成器用 `yield` 暂停/恢复函数执行，协程扩展了这概念支持 `await`（等待另一个协程）。`asyncio` 在底层用生成器实现协程，但 Python 3.5+ 通过 `async/await` 语法将协程提升为独立概念。项目同时使用了生成器（`_connect()` 上下文管理器）和协程（API 处理函数）。

**Q9: Python 3.7 vs 3.12 的主要差异？**

> 增量赋值表达式（walrus `:=`）在 3.8 引入、3.12 进一步优化；`asyncio` API 演进；类型注解语法增强（`list[str]` 而非 `List[str]`）。项目遇到 Walrus 在 Python 3.7 下的 SyntaxError。

**Q10: 255 项测试覆盖了哪些维度？测试策略是怎样的？**

> 三层测试架构：
> 1. **单元测试**（最多）：纯函数（SQL guard、path_utils）、Mock 测试（rerank、tavily）、服务测试（paper_card_service 100%、paper_matrix_service 100%、review_report_service 98%）
> 2. **集成测试**：FastAPI 路由（ASGITransport）、SQLite session store（tmp_path 隔离）、工具调用（LangChain invoke）
> 3. **端到端测试**（计划中）：Docker Compose 全栈 + 真实 MySQL/SearXNG
> 
> 覆盖 13 个模块，安全相关（18 个 SQL 注入测试、12 个路径穿越测试）是重中之重。选择 70% 覆盖率不是因为剩余 30% 不重要——而是剩下的是需要真实外部依赖的模块（embedding 模型、MySQL 连接、DeepAgents 运行时），应该由集成测试而非单元测试覆盖。

#### FastAPI / Web

**Q11: FastAPI 与 Flask 的核心区别？**

> FastAPI 基于 Starlette（ASGI），原生支持异步、WebSocket、类型校验（Pydantic）；Flask 是 WSGI，同步阻塞，生态更成熟但性能上限低。FastAPI 自动生成 OpenAPI 文档（`/docs`）。项目选择了 FastAPI 因为需要 WebSocket 实时推送和异步 Agent 任务。

**Q12: `BaseHTTPMiddleware` 的异常处理陷阱？**

> `BaseHTTPMiddleware` 内部使用 `TaskGroup` 运行中间件，`HTTPException` 在中间件中 `raise` 会被 TaskGroup 封装为 `ExceptionGroup`，不会被 FastAPI 的异常处理器捕获。项目遇到了这个问题，修正方式是将 `raise HTTPException` 改为 `return JSONResponse(status_code=..., content=...)` 并用 try/except 兜底。

**Q13: WebSocket 的 keep-alive 机制？**

> WebSocket 通过 ping/pong 帧检测连接是否存活。项目中 `websocket_endpoint` 使用 `while True: await websocket.receive_text()` 保持连接开放。客户端断开时抛出 `WebSocketDisconnect` 异常。

**Q14: Orchestrator-Workers 架构是怎么拆分的？主智能体如何决定调用哪个子智能体？**

> 1 主 Agent + 3 子 Agent 的架构在 `app/agent/main_agent.py` 中定义：
> ```python
> main_agent = create_deep_agent(
>     model=model,
>     system_prompt=main_agent_content["system_prompt"],
>     tools=[generate_markdown, convert_md_to_pdf, read_file_content],
>     checkpointer=InMemorySaver(),
>     subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
> )
> ```
> 主智能体的 system_prompt 中通过工具描述约束调用逻辑："当用户需要最新研究进展时，调用网络搜索助手；当用户需要查找论文详细信息时，调用数据库助手；当用户需要深入研读某篇论文时，调用论文知识助手"。子智能体独立定义各自的 tools 和权限范围（如 database_query_agent 只能执行 SELECT）。
> 
> 三个子智能体对应的工具函数注册在主智能体之外，通过 subagents 参数注入。这种设计的优点是：子智能体的 prompt 和工具与主智能体完全隔离，各自独立测试和维护。

**Q15: Pydantic V2 相比 V1 的变化？**

> V2 核心重写为 Rust（pydantic-core），速度提升 5-50 倍；`@validator` 改为 `@field_validator`；`Config` 改为 `model_config`。项目中 Pydantic 用于请求/响应模型定义（`TaskRequest`, `PaperCardBuildRequest` 等）。

**Q16: 评测数据——简历里说的 MRR 0.97 是怎么来的？不会是编的吧？**

> 这是真实的评测数据。我构建了 34 条 ground-truth query，覆盖 8 个 AI 主题簇（GNN、Transformer、RL、RAG、Few-shot、LLM Training、CV、Optimization），每条 query 标注了 1-4 篇目标论文，共 90 篇论文。然后跑了三种检索策略的对比：
> 
> | 策略 | Recall@3 | MRR |
> |------|----------|-----|
> | 纯向量检索 | 0.8775 | 0.8824 |
> | 混合 BM25+RRF | **0.9534** | **0.9706** |
> | 全链路 (+MiniLM rerank) | 0.8309 | 0.8676 |
> 
> 关键发现：**混合 BM25+RRF 显著优于纯向量（MRR 0.88 → 0.97）**，但加 MiniLM 重排序反而下降了。原因：重排序将候选集从 20 压缩到 10，在这个规模上丢失了部分正确文档。这说明 BM25+RRF 组合在 90 篇论文的场景下已足够好，重排序的代价（模型加载 13s + 召回损失）不值得。
> 
> 但这个结果有前提：论文是模拟生成的，embedding 模型是 all-MiniLM-L6-v2（384 维）。换 text-embedding-3-large（3072 维）纯向量的 baseline 可能更高，混合策略的优势空间会缩小。数据集和脚本完全可复现。
> 
> 这个经历给我的教训是：**"有评测"不等于"有区分度的评测"**。第一次用 17 篇论文 + 20 条简单 query 跑，所有策略 MRR 都在 0.95 以上，完全看不出差异。为了获得有区分度的结果，我生成了 80 篇模拟论文（保持标题和方法真实，内容模拟），设计了跨主题的对比 query。数据本身是模拟的，但评测框架和对比方法论是真实的——这个框架可以直接用在真实论文库上。

**Q17: 什么是 ASGI Lifespan 协议？**

> lifespan 协议定义应用启动/关闭时的生命周期事件。`@asynccontextmanager` 包装的 `lifespan` 函数在 `yield` 前执行启动逻辑（绑定 WebSocket 事件循环），`yield` 后执行清理。项目使用 `lifespan` 绑定 `manager.set_loop(loop)`。

**Q18: CORS 是什么？项目中如何配置？**

> CORS（跨域资源共享）限制浏览器跨域请求。项目中通过 `CORSMiddleware` 配置 `allow_origins=["*"]`（开发环境）或从 `CORS_ORIGINS` 环境变量读取生产域名。

**Q19: HTTP 状态码 401 vs 403 的区别？**

> 401 Unauthorized：未认证（用户未提供有效凭证）。403 Forbidden：已认证但无权限（用户知道是谁但没权限做这事）。项目中 API key 缺失返回 401，rate limiting 返回 429。

**Q20: WebSocket 和 SSE 的适用场景？**

> WebSocket：全双工，双向通信，适合实时交互（工具调用进度）。SSE：服务器 → 客户端单向流，基于 HTTP，自动重连。项目需要服务端推送 Agent 执行事件 + 客户端可能发送取消指令，所以选 WebSocket。

**Q21: FastAPI 中 `jsonable_encoder` 的作用？**

> 将 Python 对象（如 `datetime`、`UUID`、`Decimal`）转为 JSON 兼容格式。Pydantic 的 `.model_dump()` 已经内置此功能。

**Q22: ContextVar 如何实现会话隔离？为什么比 threading.local 更适合 async？**

> `ContextVar` 是 Python 3.7 引入的方案，绑定的是"上下文"而非线程。`asyncio` 是单线程并发——多个协程共享一个线程，所以 `threading.local` 不会区分它们，数据会"串台"。`ContextVar` 随 `await` 自动传播到子协程，每个协程有独立的上下文。
> 
> 项目中使用 `ContextVar("session_dir")` 存储当前会话的工作目录，每个 API 请求在入口处 `set()`，后续所有文件操作（上传保存、日志写入）通过 `get()` 获取，天然隔离。配合 `resolve_path()` 的路径校验，确保不会写入到其他会话目录。

**Q23: HTTP/2 和 HTTP/1.1 的区别？FastAPI 支持吗？**

> HTTP/2 多路复用、头部压缩、服务端推送。FastAPI（Starlette）可通过 Uvicorn 以 HTTP/2 运行（`uvicorn --http h2`），但默认是 HTTP/1.1。

**Q24: 四层 SQL 注入纵深防护是怎么设计的？**

> 四层防护从外到内：
> 1. **前缀白名单**：只允许以 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH 开头的语句
> 2. **多语句拦截**：检测分号 `;`，禁止单次调用执行多条 SQL
> 3. **关键字黑名单**：拦截 DDL（DROP/ALTER/CREATE/TRUNCATE）和 DML（INSERT/UPDATE/DELETE/REPLACE）
> 4. **表名白名单**：只允许操作 `papers`、`authors`、`paper_authors` 等预定义表名
> 
> 所有检查在 `_validate_readonly_sql()` 函数中完成，返回 `(is_valid, error_msg)`。即使突破单层检查，后续层级仍能拦截。此外，MySQL 连接使用只读用户 + `TRADITIONAL` SQL mode，SQLite 使用 `PRAGMA query_only=ON`，形成数据库级别的兜底。

**Q25: 如何处理 FastAPI 中的文件上传安全？**

> 限制文件大小、校验扩展名白名单、路径规范化防止穿越、重命名防注入。项目实现了 `_safe_upload_name()`、`MAX_UPLOAD_BYTES`、`ALLOWED_UPLOAD_SUFFIXES`。

---

### 3.2 项目设计（25 题）

**Q26: 为什么选择 DeepAgents 框架，而不是直接写 LangGraph？**

> DeepAgents 是基于 LangGraph 的上层封装，提供开箱即用的多智能体编排、工具注册、监控埋点。选择它是因为：1）减少重复开发智能体通信模板；2）内置 `stream_writer` 便于实时推送；3）专注于业务工具逻辑而非框架细节。但也因此受限于框架版本，需要对 `create_deep_agent` 的签名和配置有深入理解。

**Q27: 多源检索为什么用 RRF 融合而不是其他方式？**

> RRF（Reciprocal Rank Fusion）不需要分数归一化，对分数尺度差异大的多源结果（BM25 分数 vs 向量 cosine）天然鲁棒。公式：`score(d) = Σ 1/(k + rank_i(d))`，其中 k=30（经验值）。实验验证 k=5~60 无显著差异，取中间值保证可迁移。替代方案是 learning to rank（LTR）但需要标注数据，不适合快速迭代。
> 
> **实际效果**：在 90 篇论文的评测中，BM25+RRF 相比纯向量检索 MRR 从 0.88 提升到 0.97（+10%），Recall@3 从 0.88 提升到 0.95。这是整个流水线中贡献最大的单一设计决策。

**Q28: 证据分类的字段为什么选 problem/method/experiment/conclusion/limitation 五类？**

> 参考了论文评审表格的标准字段——任何论文都可以用这五类覆盖核心内容。分类方法基于关键词匹配（中英文），不是 NER 或文本分类模型，因为：1）不需要训练数据；2）关键词匹配结果确定性强、可调试；3）在已有证据片段上效果足够。

**Q29: 卡片 ID 为什么用 SHA256 摘要而不是 UUID？**

> 确定性——相同证据组合产出相同 card_id。避免重复提交导致重复卡片。UUID 每次生成不同，需要额外去重逻辑。SHA256 摘要前 16 位平衡了碰撞概率和可读性。

**Q30: SQLite + MySQL 双数据库的设计考量？**

> SQLite 用于会话和证据存储——无服务器、零配置、适合单机。MySQL 用于论文元数据——支持并发查询、全文索引、适合多人协作。也反映数据特性：会话/证据是应用内部状态，论文元数据是共享知识库。

**Q31: WebSocket 事件推送的设计思路？**

> 每个 Agent 任务分配 thread_id，`ConnectionManager` 用 thread_id → WebSocket 的字典维护连接。`ToolMonitor._emit()` 通过 `get_thread_context()` 获取当前 thread_id，将事件推送到对应前端。同时做三路输出：WebSocket（实时）、SQLite（历史记录）、控制台（调试）。

**Q32: 会话隔离如何实现？**

> `resolve_path()` 函数确保所有文件操作约束在当前会话目录内。任何绝对路径先检查是否在 session_dir 下，不在则降级为文件名重新解析。额外防止 `session_001/session_001/file.md` 这类嵌套路径。

**Q33: 为什么需要重排序步骤？向量检索不够吗？**

> 向量检索基于 embedding cosine，对语义相似度敏感但对细粒度相关性区分不足。MiniLM cross-encoder 对 query-doc 对计算精确匹配分数，理论上 should 提升排序精度。但在 90 篇论文的实测中，混合 BM25+RRF（MRR 0.97）已经好于全链路加重排序（MRR 0.87），原因是重排序压缩候选集导致召回损失。
> 
> 所以实际结论是：**在本项目的论文库规模下，BM25+RRF 的向量+关键词融合已经足够好，不需要 cross-encoder 重排序**。重排序在更大的候选集（1000+ 候选）和更追求 Top-1 精度的场景下才有价值。代价是 ~13s 模型加载时间，所以 `enable_reranker` 默认关闭。

**Q34: 如何保证引用可追溯？**

> `EvidenceRecord` 存储 `source`、`page`、`score`、`quote`（原文片段）。`citation_checker` 对综述中的每个声明（claim）与证据库做相似度匹配（MiniLM），输出 verified/low_confidence/unfounded 状态。匹配阈值 0.5（claim vs quote），0.25（claim vs evidence metadata）。

**Q35: Task 提交为什么设计为异步？返回 202 吗？**

> Agent 任务可能耗时 30s-5min，同步等待不现实。接口 `POST /api/task` 返回 `{"status": "started", "thread_id": ...}`。实际上是 200 不是 202，因为任务调度（创建 asyncio Task）本身是立即完成的，不需要队列确认。通过 WebSocket 推送到前端后端进展。

**Q36: Semaphore 控制并发数足够吗？还需要其他限流吗？**

> `Semaphore(4)` 控制 Agent 任务并发，防止 GPU/OOM。HTTP 层还有 `RATE_LIMIT_PER_MINUTE=60` 防止单一 IP 打满。两者配合：Semaphore 控制长时间任务，Rate Limit 控制短时间请求频率。

**Q37: Prompt 如何管理的？**

> `app/agent/prompts.py` 集中管理主智能体提示词。包含工具使用说明、输出格式要求、安全约束（如 SQL 只读）。提示词工程的关键是告诉模型工作流是什么、先搜什么后搜什么、结果如何结构化。

**Q38: 测试中遇到 AsyncClient 与 WebSocket 的限制？**

> `httpx.AsyncClient` 配合 `ASGITransport` 在大部分版本中不支持 `websocket_connect`。解决方法：1）使用 `starlette.testclient` 的 WebSocketTestSession；2）将 WebSocket 测试标记为集成测试；3）升级 httpx 到 0.28+。

**Q39: 配置管理中环境变量和配置文件的边界？**

> 环境变量覆盖运行时参数（数据库连接、API Key、超时时间）；代码内配置（`retrieval_config.py`）管理检索链路参数（RRF k、rerank model）。分离逻辑：环境变量是部署相关的，代码配置是业务逻辑不变的。

**Q40: 日志系统如何设计的？**

> `app/utils/logging.py` 封装 `configure_logging()` 和 `get_logger()`。所有日志通过 `extra` 字典传递结构化字段（`thread_id`、`request_id`、`client_ip`）。`Monitor` 额外产生 `tool_calls.log` 文件记录工具调用时间线。

**Q41: `monitor.py` 的 `ToolMonitor` 为什么是单例？**

> 确保全局只有一个监控实例，所有模块（工具、子智能体、API）复用同一个 `_emit` 方法。WebSocket 管理器和 `get_thread_context` 都在这个单例内协调。

**Q42: 如何检测 SearXNG 和 MySQL 是否可用？**

> `/health/ready` 端点对每个依赖执行实际探活：MySQL 执行 `SELECT 1`、SearXNG 发送搜索请求、SQLite 执行 `SELECT 1`。探活失败标记为 "degraded" 而非直接返回 503——系统可以在部分依赖不可用时继续运行。

**Q43: 论文卡片构建的流程是什么？**

> 1）接收 title + query + top_k → 2）LlamaIndex 检索论文片段 → 3）关键词分类（problem/method/experiment/conclusion/limitation/summary） → 4）SHA256 生成 card_id → 5）证据截取（每类 2 条 quote，每条 ≤360 字） → 6）持久化到 paper_cards 表。

**Q44: 多智能体之间如何通信？**

> 通过 LangGraph 的状态图通信。主智能体生成子任务，子智能体调用工具（搜索/查询/检索），结果写入共享状态。主智能体在汇总阶段读取所有子智能体的输出。DeepAgents 框架封装了状态管理和流式输出。

**Q45: 综述报告怎么生成的？**

> 1）从 paper_cards 表读取近期的论文卡片 → 2）`build_paper_matrix()` 转为对比矩阵 → 3）`build_review_markdown()` 按 7 段结构渲染 Markdown → 4）写入 `REPORT_DIR/session_{thread_id}/` 目录 → 5）返回文件路径和元信息。Markdown 结构：研究对象、对比矩阵、方法脉络、实验评测、主要结论、局限性、核验说明。

**Q46: API Key 认证如何做到可选？**

> 环境变量 `DISABLE_API_AUTH=true` 时中间件直接跳过认证。`API_KEY` 非空时将 `ALLOWED_API_KEYS` 初始化为集合，请求头 `X-API-Key` 匹配集合中任意一个即放行。支持多个 API Key（扩展 `ALLOWED_API_KEYS`）。

**Q47: 文件上传如何防攻击？**

> 四层防护：1）`_safe_upload_name()` 白名单扩展名（`.pdf.md.txt.docx.xlsx.xls`）；2）`MAX_UPLOAD_BYTES=20MB` 限制单文件大小；3）`MAX_UPLOAD_FILES=5` 限制批量数量；4）路径规范化后检查 `is_relative_to(target_dir)`。

**Q48: 知识库上传后索引如何更新？**

> `POST /api/knowledge/upload` 将 PDF 保存到 `PAPER_DIR` 后调用 `_load_or_build_index()` 重建 LlamaIndex。当前是全量重建，性能瓶颈——10 篇文档重建在秒级，1000 篇时需要考虑增量索引。

**Q49: RRF k 值如何调试和验证？**

> 基于 10 篇文档 + 20 条 query + 5 条中文 query 的测试集。实验结论：k=5~60 时 RRF 排序结果无显著差异，取中间值 30。验证指标是 Recall@K 和 MRR。

**Q50: 异步任务超时如何处理？**

> `asyncio.wait_for(agent_task, timeout=AGENT_TASK_TIMEOUT_SECONDS)` 包裹 Agent 执行。超时后任务 `CancelledError` 被外层捕获，标记为 cancelled。`_forget_task()` 自动从 `active_tasks` 字典清理。前端通过 WebSocket 收到 `task_cancelled` 事件。
> 
> **追问**：Timeout 值时选 300s 是拍脑袋吗？
> 基于经验值——大多数 Agent 任务在 30-120s 内完成（含网络搜索、数据库查询、模型调用）。300s 是安全边界，允许极端情况（如 SearXNG 慢、LLM API 限流退避）。如果是高频请求场景，可以降低到 120s。

---

### 3.3 场景题（25 题）

**Q51: 如果本地论文库有 10 万篇 PDF，检索延迟很高怎么优化？**

> 1）改用 FAISS 向量索引替代默认的 `SimpleIndex`；2）BM25 预计算倒排索引而非运行时构建；3）分片存储（按年份/领域分区）；4）嵌入异步预计算，上传即索引而非检索时构建；5）缓存高频查询结果；6）如果仍不够，上 Elasticsearch 作为检索后端。

**Q52: 用户并发从 10 涨到 1000，系统的瓶颈在哪里？怎么扩展？**

> 瓶颈分析：1）Python GIL + asyncio 在 CPU 密集型任务（如 embedding 计算）时阻塞；2）SQLite 写入竞争（WAL 模式缓解但仍有上限）；3）SearXNG 单实例吞吐有限；4）DeepAgents/LangGraph 是单进程状态图。
>
> 扩展方案：1）Agent 执行分离到独立进程池（`process_pool_executor`）或 Worker 容器；2）SQLite → PostgreSQL 或 MySQL；3）SearXNG 水平扩展；4）引入消息队列（Redis/RabbitMQ）做任务缓冲；5）API 层无状态化，通过负载均衡扩展。

**Q53: 检索结果与用户查询完全无关，如何排查问题？**

> 排查链路：1）检查 embedding 模型——`.env` 中 `LLAMAINDEX_EMBED_MODEL=mock` 会导致向量完全随机；2）检查 BM25 tokenizer——英文论文用 jieba 分词效果差；3）检查 `candidate_multiplier` 是否太小导致候选池不足；4）检查 `enable_reranker`——关闭状态下仅靠 BM25+向量可能排序不佳；5）查看 `EvidenceRecord` 的 `score` 和 `source` 确认数据源是否正确；6）检查索引是否成功构建（`_load_or_build_index`）。

**Q54: 一个 Agent 任务跑了 30 分钟还没结束，你怎么处理？**

> 当前机制：`AGENT_TASK_TIMEOUT_SECONDS=300`（5 分钟），超时自动 cancel。如果仍有任务超长：1）检查子智能体是否进入死循环（LangGraph 最大步数限制）；2）检查外部依赖（SearXNG/MySQL）是否响应；3）添加最大 token 限制防止模型无限生成；4）设置 Progress Callback 定期汇报状态。

**Q55: 如果用户上传了一个 2GB 的 PDF，会发生什么？怎么改进？**

> 当前会触发 `MAX_UPLOAD_BYTES=20MB` 限制返回 400。如果要去除限制：1）流式处理——边上传边读取，不加载全文到内存；2）PDF 分页提取，每页独立 embedding；3）限制上传速度（nginx `proxy_request_buffering`）；4）异步处理——上传后立即返回，后台构建索引。

**Q56: 如果数据库被注入攻击成功，如何从代码层面防止？**

> 当前已实现：1）`_validate_readonly_sql()` 白名单校验，只允许 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH；2）禁止分号（多语句）、禁止 DDL/DML 关键词；3）MySQL 连接使用只读用户；4）查询参数化（虽然当前是 raw SQL，但可以改为 ORM + 参数化查询）。进一步：5）数据库连接设置 `read_only=1` 全局锁写；6）SQLite 设为 `PRAGMA query_only=ON`。

**Q57: 任务提交后，用户在 WebSocket 断连了，任务还在运行吗？**

> 是。`active_tasks` 字典保存的是 `asyncio.Task` 对象，与 WebSocket 连接无关。用户重连后可以重新通过 thread_id 获取任务状态。但如果用户不重连，任务会持续在后台运行直到完成或超时。可以改进：添加 TTL 策略，如果 WebSocket 断连超过 N 分钟且任务未完成，自动 cancel。

**Q58: 如何实现不同用户的完全隔离？**

> 当前只有会话隔离（thread_id 级别），没有用户系统。如果要加：1）用户认证层（JWT/OAuth）；2）用户 ID 作为所有数据表的前缀字段；3）API Key 与用户绑定；4）论文卡片/证据/会话都按 `user_id` 过滤；5）用户级别资源配额（max_tasks、disk_quota）。

**Q59: Embedding 模型加载缓慢，如何优化首次请求延迟？**

> 当前模型在首次使用时延迟加载（`_load_reranker` 的缓存模式）。优化方案：1）启动时预加载（lifespan 事件中）；2）使用更轻量模型（`all-MiniLM-L6-v2` 已经是最轻量之一）；3）模型量化（ONNX Runtime、FP16）；4）模型服务化（独立部署 embedding 服务，API 调用而非本地加载）。

**Q60: 测试随机失败，排查步骤是什么？**

> 1）检查是否是测试顺序依赖——单独跑该测试 vs 全量跑；2）检查全局状态污染——`importlib.reload`、环境变量修改、SQLite 路径切换是否对称恢复；3）检查异步竞争条件——`asyncio` 测试是否用了 `asyncio.run()` 而非手动管理 loop；4）检查临时文件清理——`TemporaryDirectory` 在 yield 后自动删除可能导致后续测试找不到文件；5）检查 Mock 泄漏——`monkeypatch` 是否在 teardown 中恢复。

**Q61: Monorepo 中如何管理前端和后端的 CI/CD？**

> 前端和后端分离的 pipeline：后端 run pytest + coverage + security scan；前端 run jest + lint + build。Docker 构建：`docker-compose build` 并行构建前后端镜像。本项目中前端代码不在同一仓库，后端通过 Docker 部署。

**Q62: 如果 SearXNG 服务挂了，系统应该怎么表现？**

> 当前 `/health/ready` 会标记 SearXNG 为不可用，但系统继续运行。网络搜索子智能体在调用失败时应返回友好的错误信息而非崩溃。可以实现：1）网络搜索降级到纯 Tavily；2）缓存历史搜索结果；3）向用户提示 "公开搜索暂时不可用，本地论文库检索正常"。

**Q63: BM25 和向量检索的融合权重如何调优？**

> 当前使用 RRF 融合，不需要权重参数。如果要加权：1）在 RRF score 前加系数 `score = w_bm25 * f_bm25 + w_dense * f_dense`；2）通过网格搜索或贝叶斯优化在验证集上调参；3）评估指标：Recall@K、NDCG@K。

**Q64: 如何验证引用校验的准确性？**

> 构建标注数据集：1）人工标注 claim-evidence 对（match / partial / no match）；2）在不同 similarity 阈值下计算 precision/recall；3）当前阈值 (0.5/0.25) 是基于实验的保守设置——宁可漏标不可误标；4）可添加人工审核界面，让用户确认/修正校验结果。

**Q65: 你的测试覆盖了哪些模块？最重要的测试是什么？**

> 新增 128 个测试，覆盖 13 个模块。最重要的三组：1）SQL 注入防护测试（18 个）——安全底线；2）测试隔离验证——确保 255 个测试可以任意顺序执行；3）论文卡片服务测试（11 个，100% 覆盖）——核心业务逻辑。最关键的 bug 修复是 SQLite 路径泄漏和中间件异常传播。

**Q66: Docker 部署时，SQLite 文件如何持久化？**

> 通过 Docker volume 挂载：`docker-compose.yaml` 中 `volumes: - ./data:/app/data`。确保 `SESSIONS_DB_PATH` 和 `REPORT_DIR` 指向 volume 映射的目录。注意 SQLite 在 NFS 上表现不佳，生产应使用本地 SSD 存储。

**Q67: 如果用户关闭浏览器，WebSocket 断开，后台 Agent 是否继续？**

> 是。`active_tasks` 中的 `asyncio.Task` 与 WebSocket 生命周期解耦。`WebSocketDisconnect` 触发 `manager.disconnect()` 清理连接，但不影响 Agent 执行。Agent 完成后再推送时发现无连接则降级到 SQLite 存储 + 日志文件。

**Q68: 四层 SQL 注入防护在测试中是如何验证的？有没有遗漏的绕过路径？**

> 测试：18 个专门的 SQL 注入测试用例，覆盖常见注入手法——`UNION SELECT`、`; DROP TABLE`、`OR 1=1`、注释绕过、大小写绕过、编码绕过等。每个测试验证 `_validate_readonly_sql()` 返回 False。
> 
> 已知的绕过风险：1）前缀白名单是以 SQL 关键字开头判断，不会解析 AST——`SELECT` 可以隐藏在注释中（`/**/SELECT`）；2）关键字黑名单是字符串匹配，`DROP` 作为子字符串可能被误杀（如 `DROPPING`），所以用了 `r'\bDROP\b'` 正则；3）MySQL 的 `/*!SELECT*/` 语法在 `TRADITIONAL` SQL mode 下失效，但仍有理论风险。
> 
> 真正的兜底不是代码层的校验，而是数据库权限——MySQL 用只读用户、SQLite 用 `PRAGMA query_only=ON`，即使校验被绕过，写入操作在数据库层也会被拒绝。

**Q69: 综述报告中如果引用了错误的信息，如何追溯？**

> 每个 `EvidenceRecord` 记录了 `source`、`page`、`quote` 和 `score`。如果报告引用出错：1）通过 `CitationCheck` 查看 claim 匹配的证据 ID；2）从 `EvidenceRecord` 获取原文片段和页码；3）回到原始 PDF 文件验证。整个过程可以通过 `GET /api/report/{id}/verification` 获取。

**Q70: 你在测试中使用了 monkeypatch，为什么不用 unittest.mock？**

> `monkeypatch` 是 pytest 内置的，与 fixture 生命周期自动集成——修改在测试结束后自动恢复。`unittest.mock.patch` 需要手动 `start()`/`stop()` 或 with 语句。`monkeypatch.setattr` 更简洁。但 `monkeypatch` 不适用于 `from X import func` 场景（需要 patch 目标模块而非源模块），这是项目中踩过的坑。

**Q71: 用户搜索 "transformer attention" 时，系统如何处理？**

> 1）主智能体分发任务 → 2）网络搜索子智能体通过 SearXNG 搜索公开资料 → 3）论文知识子智能体通过 LlamaIndex（BM25+向量）检索本地论文 → 4）数据库子智能体查询 MySQL 论文元数据 → 5）RRF 融合多源结果 → 6）MiniLM 重排序 → 7）证据分类 (problem/method/experiment) → 8）格式化为结构化证据返回 → 9）可选的卡片构建和综述生成。

**Q72: 测试文件 test_server.py 中的 `asyncio.run(_test())` 模式有什么问题？**

> 1）每次测试创建新事件循环，无法复用 loop-bound 资源；2）如果 fixture 是异步的（如 `ASGITransport` 的 `AsyncClient`），`asyncio.run()` 在协程外调用；3）重复创建/销毁 loop 的开销。更推荐用 `pytest-asyncio` 的 `@pytest.mark.asyncio` 装饰器。

**Q73: 你这个系统能用于实际科研吗？局限性在哪？**

> 可以辅助文献调研和综述初稿生成，但不适合作为定稿工具。局限性：1）证据分类基于关键词匹配而非语义理解，可能分类不准确；2）综述报告是 Markdown 初稿，需要人工核验和补充；3）Embedding 模型在专业领域可能效果不如通用 NLP 任务；4）缺少用户反馈闭环（无法根据用户修正改进）。

**Q74: 如果 review_report_service 的 `write_review_report` 并发调用会怎样？**

> 文件名包含时间戳（`%Y%m%d_%H%M%S`），毫秒级并发会生成不同文件，不会覆盖。但 `thread_id` 相同且在同一秒内提交时，session 目录可能创建重复文件。低概率冲突，且 .md 文件被覆盖也不会数据丢失（前一个版本还在）。

**Q75: 为什么选择测试覆盖率 70% 而不是追求 100%？**

> 剩余 30% 是三类模块：1）需要真实外部模型/服务（llamaindex_tools: embedding、rerank_tools: MiniLM）；2）需要真实数据库连接（db_tools: MySQL）；3）需要完整 DeepAgents 运行时（main_agent）。这些应该由集成/端到端测试覆盖而非单元测试。追求 100% 单元覆盖率会导致测试过于脆弱（大量 mock 外部依赖，测试价值递减）。

---

### 3.4 HR 综合（25 题）

**Q76: 简单介绍这个项目，如果你是技术 leader 怎么向非技术人员介绍？**

> "这是一个帮助科研人员自动写文献综述的系统。你上传一堆论文 PDF，系统会自动搜索资料、提取关键信息（研究问题、方法、实验结果等），然后把这些信息整理成一篇结构化的文献综述初稿。整个过程中，系统会实时告诉你它在做什么——搜了什么、查了什么、找到了什么，而且每个结论都能追溯到原文的哪一页。"

**Q77: 这个项目最困难的技术挑战是什么？**

> 测试隔离问题。一开始 128 个测试中有 8 个持续失败，排查发现不是业务代码的问题，而是测试之间互相污染状态——一个测试改了全局 SQLite 路径不恢复，后面 20 个测试全挂。修复这个涉及到理解 Python 模块缓存机制、`importlib.reload` 的行为、`monkeypatch` 的生效范围。解决了这个问题后，128 个测试全部稳定通过。

**Q78: 你在项目中最大的收获是什么？**

> 工程交付和测试基础设施的思维方式。一个系统好不好，看它的测试就知道——测试是否稳定、是否能快速定位问题、是否容易添加新测试。我学会了在设计测试时就要考虑隔离性，否则测试越多维护成本越高而不是越低。

**Q79: 如果让你重新设计这个项目，你会做什么不同？**

> 1）检索层解耦——将 LlamaIndex 封装成独立服务，方便独立扩展和测试；2）测试策略前置——先写测试再写代码（TDD 不一定要完全遵守，但至少在写新模块时同步写测试）；3）异步统一——测试全部用 `pytest-asyncio` 而非混合 `asyncio.run()`；4）用户系统——从第一天就设计多租户隔离，后期加的成本很高。

**Q80: 你在这个项目中扮演什么角色？**

> 全栈开发和测试架构设计。负责：1）测试体系从 128 到 255 个测试的扩增和全部修复；2）API 认证和安全加固；3）中间件异常处理重构；4）检索管线参数调优；5）路径解析和安全校验；6）生产日志系统搭建。

**Q81: 和团队协作中遇到的分歧？怎么解决的？**

> （根据实际经历准备，如果没有可以说通用情况：关于是否应该花时间加固测试基础设施的分歧——有人认为测试够用就行，但实践证明不稳定的测试比没有测试更糟糕，因为会降低团队对测试的信任。解决方式：先在一个模块做 demo 展示修复前后对比，用数据说话。）

**Q82: 如果用户反馈系统很慢，你怎么排查？**

> 分层排查：1）API 层看响应时间分布（FastAPI 内置 metrics）；2）Agent 执行时间（Semaphore 等待时间 + 实际执行时间）；3）检索时间（LlamaIndex 构建/查询、BM25）；4）外部依赖（SearXNG 响应、MySQL 查询）。瓶颈大多在 embedding 计算和模型加载。

**Q83: 你如何确保代码质量？**

> 三层保障：1）测试层——255 个自动化测试，CI 强制通过；2）代码审查——有 `review` 技能辅助 PR review；3）安全扫描——基础的安全测试（SQL 注入、路径穿越）作为回归。还有 `simplify` 技能做代码复用和质量检查。

**Q84: 你在测试中发现了什么让你印象深刻的 bug？**

> 中间件异常传播问题。`BaseHTTPMiddleware` 中用 `raise HTTPException` 看起来正确，但在 ASGI 测试中会变成 `ExceptionGroup` 导致测试崩溃。这个 bug 只影响测试不影响生产（因为生产用 Uvicorn 运行，中间件异常由 Uvicorn 处理）。但如果你不能自动化测试认证逻辑，你就不敢改认证代码——这才是真正的问题。

**Q85: 你如何持续学习新技术？**

> 这个项目本身就是学习的过程：第一次用 DeepAgents、LangGraph、LlamaIndex；测试中发现了预期的行为差异（monkeypatch 层级、异步测试模式）后，通过读源码和实验验证理解底层机制。面试中可以提到最近在研究什么（比如你正在看的领域相关技术）。

**Q86: 对这个项目后续的 roadmap 有什么想法？**

> 1）增量索引——当前每次知识库上传都全量重建；2）用户系统——多租户、权限、存储隔离；3）Embedding 服务化——独立部署 embedding 服务；4）检索评估——建立标注集评估 Recall/Precision；5）前端增强——证据可视化、可交互的综述编辑。

**Q87: 为什么用 SQLite 不用 PostgreSQL？**

> SQLite 零配置、文件级备份、对单机应用性能足够。PostgreSQL 适合多进程高并发场景。项目中的 SQLite 存的是会话和证据，访问模式是单机单进程，SQLite 完全胜任且简化部署。

**Q88: 你如何看待技术债务？这个项目有哪些技术债务？**

> 技术债要区分"有意识的技术债"和"无意识的低质量代码"。有意识地接受技术债是正常的（比如优先做功能验证再做完善），但必须记录在案。当前债务：1）索引全量重建；2）证据分类仅关键词匹配；3）MySQL 查询未参数化（虽然已限制只读）；4）前端缺失。

**Q89: 在一个 deadline 很紧的 sprint 里，你如何平衡测试和功能开发？**

> 核心原则：关键路径必须有测试。安全相关（认证、文件上传、SQL 查询）、核心业务（证据分类、卡片生成）必须有自动化测试。UI 和体验类可以延后。这个项目就是按这个优先级推进的——先做了安全测试、服务层全覆盖，再补工具和边界测试。

**Q90: 描述一次你不得不回退代码的经历。**

> （根据实际情况准备。通用：测试发现了一个关键路径的 bug 需要回退一个 commit。从中学到了应该在小的原子 commit 上工作，方便定向回退。）

**Q91: 这个项目对性能有要求吗？你做了哪些优化？**

> 主要关注延迟和吞吐。优化：1）Semaphore 控制并发防止 OOM；2）RRF 代替向量检索的多次查询；3）模型延迟加载（`_load_reranker` 缓存）；4）连接池复用 SQLite/MySQL 连接；5）MiniLM 重排序可按需关闭。

**Q92: 你是如何做技术选型的？比如 FastAPI vs Flask？**

> 需要异步、WebSocket → 排除 Flask（WSGI）。需要类型校验 → FastAPI 内置 Pydantic。需要实时推送 → FastAPI + WebSocket。生态成熟度 → FastAPI 已经是 Python Web 框架的事实标准。最终选择 FastAPI，没有纠结。

**Q93: 你如何看待 AI 辅助编程？**

> AI 是加速器不是替代者。好的工程师用 AI 加快 2-3 倍编码速度，但架构设计、测试策略、安全意识和系统思维是 AI 替代不了的。这个项目大量使用了 AI 辅助，但测试的隔离性设计和 bug 的根因分析是人为判断的。

**Q94: 如果需要你给一个初级工程师讲解这个系统的测试设计，你会怎么讲？**

> "测试是一个投资——现在写测试花时间，未来改代码省时间。关键原则：1）每个测试独立——你的测试不应该因为别人跑了别的测试而失败；2）测行为不测实现——不关心代码怎么写，关心输入输出对不对；3）纯函数测逻辑，集成测流程——不用 mock 去测可以直接调的函数。"

**Q95: 如何衡量测试的有效性？**

> 指标：1）通过率（100% 是底线）；2）代码覆盖率（关注趋势不关注绝对值）；3）测试执行时间（慢到没人跑就没用）；4）缺陷逃逸率（上线后 bug 数 / 测试发现 bug 数）。最重要的是第 4 个——如果 CI 全绿但上线后 bug 不断，说明测试没测到真正的问题。

**Q96: 如果你要带一个实习生完成类似项目，你会怎么安排任务？**

> 第一阶段：熟悉代码库——从文档和测试开始，修复一个简单 bug。第二阶段：写一个模块的完整测试——理解被测模块后设计测试用例。第三阶段：实现一个小功能——从头到尾包括测试。这样的节奏既能交付也能成长。

**Q97: 你如何应对"这个功能不需要测试"的观点？**

> 有道理的场景：原型验证、一次性脚本、简单的前端展示。但项目中的核心逻辑（证据分类、SQL 校验、路由处理）必须有测试。关键在于区分"不写测试也安全的代码"和"不写测试很危险的代码"。

**Q98: 你的测试发现过生产环境的 bug 吗？**

> 测试中发现了中间件异常传播问题——`raise HTTPException` 在测试中不可见，虽然生产环境因为 Uvicorn 的行为差异不会暴露，但如果没有测试覆盖认证逻辑，后续的认证改动能完全没有信心。还发现了 test_production_hardening 的 SQLite 路径泄漏，虽然这个不是生产 bug。

**Q99: 你如何在团队中推动更好的工程实践？**

> 用事实说话，不用理论。比如：先展示 8 个测试为什么失败（都是测试隔离问题），然后展示修复后 128 个测试全部通过，然后在 PR 模板里加测试 checklist。一步一步来，不要求一次性改革。

**Q100: 未来一年你想在技术上成长什么？**

> 我希望能深入大模型应用的可观测性和评估——不仅仅是让系统跑通，而是能系统地衡量检索质量、智能体决策质量、引用的准确性。这需要对 RAG 评估体系（如 RAGAS、TruLens）有深入理解，并能够应用到实际项目中。（根据你的实际目标调整）

---

## 4. 改进思路与落地

### 4.1 已落地改进（7 项）

| 改进 | 动机 | 做法 | 效果 |
|------|------|------|------|
| 测试体系 128→255 | 覆盖率不足、测试不稳定 | 新增 13 个测试文件 127 个净增测试 | 57%→70%，128→255，0 fail |
| 中间件异常处理 | `raise HTTPException` 在 ASGI 中不被捕获 | 改为 `return JSONResponse` + try/except | 认证测试可正常执行 |
| SQLite 路径泄漏修复 | 测试改全局路径不恢复 | `set_session_db_path(_orig)` 对称恢复 | 消除 20 个 false failure |
| 测试状态污染修复 | `importlib.reload` 不清理 | module-scoped cleanup fixture | 任意顺序执行不互相影响 |
| Walrus 兼容性 | Python 3.7 SyntaxError | 改为传统 while True + break | 多 Python 版本兼容 |
| Monkey Patching 修复 | `from X import func` 本地引用问题 | patch 目标模块而非源模块 | mock 在所有场景下生效 |
| 检索评测数据矫正 | 实际跑 eval 发现天花板效应，MRR/Recall 数据无法复现 | 扩论文库至 90 篇（模拟），设计 34 条有区分度的 ground-truth query | MRR 纯向量 0.88 → 混合 0.97，Recall@3 从 0.88 到 0.95 |

### 4.2 规划中改进（5 项）

| 改进 | 优先级 | 思路 |
|------|--------|------|
| 增量索引 | P0 | 监听文件变化→仅增量构建 embedding，避免全量重建 |
| Embedding 服务化 | P1 | 独立部署 sentence-transformers 服务，通过 HTTP 调用而非本地加载 |
| 集成测试环境 | P1 | Docker Compose 启动所有依赖（MySQL、SearXNG），CI 中运行端到端测试 |
| 评测集扩大与区分度改进 | 已完成 | 扩至 90 篇论文 + 34 条 query，三种策略差距显著拉开 |
| 检索评估管线 | P2 | 构建标注 query-evidence 集，在 CI 中跟踪 Recall/Precision 趋势 |

---

## 5. 测试过程与结果

### 5.1 测试策略

```
分层测试架构
    ├── 单元测试（最快、最多）
    │   ├── 纯函数测试（SQL guard、path_utils、tokenize）
    │   ├── Mock 测试（rerank、tavily、db_tools config）
    │   └── 服务测试（paper_card、matrix、review_report）
    │
    ├── 集成测试（需模块加载）
    │   ├── FastAPI routes（ASGITransport）
    │   ├── SQLite session store（tmp_path + 隔离）
    │   └── 工具调用（LangChain invoke）
    │
    └── 端到端测试（计划中）
        ├── Docker Compose 全栈
        └── 真实 MySQL + SearXNG
```

### 5.2 测试数据

```
改进前:  128 个测试, 94% 通过率, 57% 覆盖率, 8 个失败
改进后:  255 个测试, 100% 通过率, 70% 覆盖率, 0 个失败
新增:    13 个测试文件, 127 个净增测试, 11 个模块覆盖率提升
运行时间: ~80s (含 coverage 报告)
```

### 5.3 模块覆盖详情

| 模块 | 之前 | 之后 | 变化 |
|------|------|------|------|
| paper_card_service | 0% | 100% | +100pp |
| paper_matrix_service | 41% | 100% | +59pp |
| review_report_service | 84% | 98% | +14pp |
| rerank_tools | 0% | 84% | +84pp |
| tavily_tool | 0% | 87% | +87pp |
| monitor | 58% | 84% | +26pp |
| path_utils | 84% | 95% | +11pp |
| markdown_tools | 22% | 65% | +43pp |
| pdf_tools | 34% | 77% | +43pp |
| upload_file_read_tool | 22% | 52% | +30pp |
| word_converter | 16% | 60% | +44pp |
| **总计** | **57%** | **70%** | **+13pp** |

### 5.4 Bug 修复清单

| # | Bug | 根因 | 修复内容 | 影响范围 |
|---|------|------|----------|----------|
| 1 | server.py:518 SyntaxError | walrus 运算符 Python 3.7 不支持 | while 循环改写 | 全局无法运行 |
| 2 | 中间件 401/429 不生效 | `BaseHTTPMiddleware` + `raise HTTPException` | 改为 `JSONResponse` + try/except | auth 测试全部失败 |
| 3 | 20 个 server 测试 `no such table` | 全局 SQLite 路径在 temp dir 销毁后未恢复 | `set_session_db_path(_orig)` | 测试隔离 |
| 4 | Auth 测试后 server 测试 401 | `importlib.reload` 不恢复环境变量 | module-scoped cleanup fixture | 测试隔离 |
| 5 | Monkeypatch 不生效 | `from X import func` 本地引用问题 | 在目标模块 patch | 工具测试全部失败 |
| 6 | 空 query 测试预期错误 | 服务端只拦 >2000，空字符串不拦 | 改测试预期 200 | 不修复业务代码 |

### 5.5 检索评测结果

基于 90 篇模拟论文（8 个主题簇 × ~10 篇/簇）+ 34 条 ground-truth query（单篇精确、多篇对比、精确数值三类难度）：

| 策略 | Recall@3 | Recall@5 | Recall@10 | MRR | 相对提升 |
|------|----------|----------|-----------|-----|----------|
| 纯向量检索（baseline） | 0.8775 | 0.9412 | 0.9902 | 0.8824 | — |
| 混合 BM25+RRF | **0.9534** | **0.9681** | **0.9902** | **0.9706** | **+10.0% MRR** |
| 全链路（+MiniLM 重排序） | 0.8309 | 0.9069 | 0.9902 | 0.8676 | -1.7% MRR |

> **关键洞察**：BM25+RRF 是最大贡献者，MRR 0.88→0.97（+10%）。MiniLM 重排序在本场景中反而有害（MRR 0.87），因为它将候选集从 20 压缩到 10 的过程中丢失了正确文档。结论：在小到中等规模论文库，BM25+向量融合已足够好，Cross-encoder 重排序更适合大规模候选集（1000+）下的 Top-1 精排场景。

评测配置：`rrf_k=30`, `candidate_multiplier=2`, `embedding=all-MiniLM-L6-v2`（384维），MockEmbedding 模式生成索引。数据集和评测脚本在 `scripts/generate_papers.py` 和 `app/evaluation/evaluate.py`，完全可复现。

---

## 6. 项目设计困难与取舍

### 6.1 架构取舍

| 决策 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| AI 框架 | DeepAgents | 裸 LangGraph / 自研 | 减少模板代码，快速验证 |
| 检索融合 | RRF | 加权求和 / Learning to Rank | 零参数、分数尺度无关 |
| 证据分类 | 关键词匹配 | NER 模型 / 文本分类 | 确定性强、无训练成本 |
| 数据库 | SQLite + MySQL | 统一用 MySQL | 简化部署、按数据特性分离 |
| 卡片 ID | SHA256 | UUID | 确定性去重 |
| 重排序 | 按需启用 | 默认开启 | 节省模型加载时间 |
| 测试框架 | pytest + monkeypatch | unittest.mock | 与 fixture 集成更好 |

### 6.2 遇到的困难

**困难 1：多智能体调试困难**
- 表现：Agent 任务报错时难以定位是哪个子智能体或工具的问题
- 解决：完善 monitor 系统，每个工具调用都 `report_tool`，每个子智能体调用都 `report_assistant`，所有事件同时推送到 WebSocket + SQLite + 日志文件三层输出
- 教训：可观测性不能事后添加，应该在第一天就设计进去

**困难 2：测试隔离与状态泄漏**
- 表现：测试全量跑有 8 个失败，但单独跑全部通过
- 解决：排查发现 `importlib.reload` 不恢复环境变量、SQLite 路径泄漏、monkeypatch 层级错误三个根因
- 教训：模块级全局状态是测试的天敌。所有改全局状态的代码必须提供对称的恢复接口

**困难 3：检索效果难以量化，小样本评测存在天花板效应**
- 表现：建立了 20 条 query 的 ground-truth 评测集，但实际跑出来的 MRR 普遍在 0.92-0.95，三种策略之间几乎没有差距
- 根因：论文库仅 ~17 篇 PDF，20 条 query 覆盖 ~10 篇唯一论文，纯向量检索已经能轻松命中目标——评测任务太简单，不同策略拉不开差距
- **解决**：生成了 80 篇模拟论文（覆盖 8 个 AI 主题簇），重新设计 34 条 query（含单篇精确、多篇对比、精确数值三类难度）。在新的 90 篇论文 + 34 query 的评测集上，三种策略拉开了清晰差距：纯向量 MRR=0.88，混合 BM25+RRF MRR=0.97，全链路 MRR=0.87
- 发现：**BM25+RRF 是最大贡献者，MiniLM 重排序反而降低效果**。这对简历数据是个重要的矫正——之前以为 MiniLM 是提升的关键，实测发现真正的贡献来自 BM25 的精确匹配能力
- 教训：评测集的"区分度"比"数量"更重要。花时间标注 ground truth 是第一步，验证评测集能区分不同策略才是关键。以及："加一层模型"不等于"效果更好"，必须用数据验证每个设计决策

**困难 4：测试隔离与状态泄漏**
- 表现：测试全量跑有 8 个失败，但单独跑全部通过
- 解决：排查发现 `importlib.reload` 不恢复环境变量、SQLite 路径泄漏、monkeypatch 层级错误三个根因
- 教训：模块级全局状态是测试的天敌。所有改全局状态的代码必须提供对称的恢复接口

**困难 5：Python 版本兼容性**
- 表现：`pyproject.toml` 要求 3.12，但系统默认 Python 是 3.7
- 解决：使用 `.venv` 隔离环境，但 walrus 运算符在早期版本不兼容
- 教训：如果代码需要在多种环境运行，不要使用新语法特性（或明确文档化版本要求）

**困难 6：LangChain 工具与 ASGI 测试的集成**
- 表现：`@tool` 装饰器注册的工具在测试中行为与生产不同
- 解决：使用 `tool.invoke()` 方法而非直接调用函数
- 教训：框架封装越厚，测试时越需要理解框架行为

### 6.3 技术债务清单

1. **检索全量重建** — 每次知识库上传重建索引，O(n) 增长
2. **证据分类关键词匹配** — 无法理解语义、不能处理未知词
3. **MySQL 查询未参数化** — 虽有限只读校验，但不是最优实践
4. **单进程 SQLite** — 无法水平扩展
5. **无用户系统** — 数据完全共享
6. **前端未开源** — 无法完整演示
7. **评测数据为模拟论文** — 90 篇论文是模拟生成，非真实 PDF 全文

---

## 7. 简历 Hook 地图 — 面试官会问什么

### 7.1 总览：4 个子弹头的 Hook 分布

```
简历文本 → 面试官看到的关键词 → 会追问的方向

子弹1: "Orchestrator-Workers 架构，WebSocket 实时推送，SQLite WAL 持久化，断线重连"
  → 架构设计、多智能体通信、实时性方案、持久化选型

子弹2: "LlamaIndex 向量 + BM25 + RRF + MiniLM，34 条 ground-truth，MRR 0.97"
  → 检索策略选择、RAG 评估方法论、数据真实性、天花板效应教训

子弹3: "证据记录 → 论文卡片 → 对比矩阵 → Markdown 综述"
  → 提示词工程、信息抽取策略、确定性 vs 模型推理

子弹4: "API Key 鉴权、四层 SQL 注入防护、ContextVar 会话隔离、255 项测试、三种 embedding 模式"
  → 安全设计、测试策略、工程化思维、配置管理
```

### 7.2 子弹 1 深度拆解：多源检索 Agent + 可观测机制

**简历原文**：
> 基于 DeepAgents 与 LangGraph 设计 Orchestrator-Workers 架构（1 主 Agent + 3 子 Agent），拆分网络搜索、数据库查询、本地论文库检索三条工具链路；设计 WebSocket 实时事件推送与 SQLite WAL 持久化，Agent 每一步 tool_call 与决策事件即时推送至前端，支持断线重连后历史事件回放，提升多步骤任务的执行透明度与调试效率。

**Hook 1："Orchestrator-Workers" → 会问多智能体架构**

预期追问："主 Agent 怎么知道调用哪个子 Agent？是规则还是模型决定的？"

> 主 Agent 的 system_prompt 中用工具描述约束调用逻辑——不是硬编码规则，也不是模型自由发挥。在 `app/agent/prompts.py` 中定义了"当用户需要最新研究进展时，调用网络搜索助手；当用户需要查找论文详细信息时，调用数据库助手"。三个子 Agent 通过 `create_deep_agent` 的 `subagents` 参数注入，子 Agent 各自独立定义 tools 和权限范围。

**代码结构** (`app/agent/main_agent.py:38-44`)：
```python
main_agent = create_deep_agent(
    model=model,
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)
```

> 主 Agent 的 tools（3 个文件工具）和 subagents（3 个子 Agent）是分开注册的。tools 是主 Agent 直接调用的功能，subagents 是委托给子 Agent 的复杂任务。DeepAgents 框架在底层把 subagents 封装成 tool 暴露给主 Agent。

**Hook 2："WebSocket 实时推送" → 会问为什么不用 SSE / 轮询**

预期追问："WebSocket 断连后 Agent 还在跑吗？用户怎么恢复？"

> 断连后 Agent 继续运行不受影响。`active_tasks` 字典保存的是 `asyncio.Task` 对象，与 WebSocket 连接解耦。重连后通过 `GET /api/task/{id}/events` 拉取历史事件（从 SQLite `run_events` 表读取），然后继续接收实时事件。核心设计：WebSocket 负责实时，SQLite 负责持久化，两者独立。
> 
> **代码** (`app/api/monitor.py`)：`ConnectionManager` 以 `thread_id → WebSocket` 字典维护连接。`ToolMonitor._emit()` 三路输出：WebSocket（实时）、SQLite（历史）、控制台（调试）。

**Hook 3："SQLite WAL 持久化" → 会问为什么不用 JSON 文件**

预期追问："SQLite WAL 有什么坑？并发写时遇到过问题吗？"

> 原版用 JSON 文件存储会话，多用户并发写时文件互相覆盖。SQLite WAL（Write-Ahead Logging）解决并发问题：允许多个读事务和单个写事务同时进行。关键坑：SQLite 默认 `BEGIN` 是 DEFERRED 的，在高并发写时容易撞上 `SQLITE_BUSY`。必须用 `BEGIN IMMEDIATE` 一进事务就声明写意向。
> 
> WAL 模式的优势：读不阻塞写，写不阻塞读。代价是 WAL 文件会增长，需要定期 checkpoint。在单机应用场景下完全够用。

**Hook 4："执行透明度与调试效率" → 会问具体怎么调试 Agent**

> ToolMonitor 的 `_emit()` 在工具调用开始时记录 `tool_start`，结束时记录 `tool_end`，子智能体调用时记录 `assistant_start`。所有事件带时间戳和 thread_id，写入 `tool_calls.log`。出问题时可以按 thread_id 过滤日志，精确看到每一步的输入输出。比 LangChain AgentExecutor 的黑盒重试好排查得多。

### 7.3 子弹 2 深度拆解：多策略检索与融合排序流水线

**简历原文**：
> 基于 LlamaIndex 建立本地论文向量索引（chunk_size=512, overlap=64），叠加 BM25 关键词精确匹配与 RRF 无参数排序融合；构建 34 条 ground-truth 评测集（8 主题簇 × 3 难度等级）进行三维策略 A/B 对比，混合 BM25+RRF 策略 MRR 0.97（纯向量 0.88 → 混合 0.97，Recall@3 提升 0.08），返回含来源、页码和原文片段的结构化证据用于引用校验。

**Hook 1："chunk_size=512, overlap=64" → 会问参数怎么选的**

预期追问："chunk_size 为什么是 512 不是 256 或 1024？有实验依据吗？"

> 512 是学术论文摘要 + 方法描述的典型长度。短了（256）信息不完整，长了（1024）引入噪音。overlap=64（12.5%）保证跨 chunk 的信息不丢失。参数从 LlamaIndex 默认值继承（chunk_size=1024, overlap=200），针对论文场景下调——论文文本密度高，小 chunk 能得到更精准的匹配。
>
> 这个参数在 `app/tools/llamaindex_tools.py:229-231` 配置，可通过 `LLAMAINDEX_CHUNK_SIZE` 和 `LLAMAINDEX_CHUNK_OVERLAP` 环境变量覆盖：
> ```python
> CHUNK_SIZE = int(os.getenv("LLAMAINDEX_CHUNK_SIZE", "512"))
> CHUNK_OVERLAP = int(os.getenv("LLAMAINDEX_CHUNK_OVERLAP", "64"))
> ```

**Hook 2："RRF 无参数排序融合" → 会问 RRF 公式和 k 值**

预期追问："RRF 的 k=30 是怎么确定的？为什么不用加权平均？"

> RRF 公式：`score(d) = Σ 1/(k + rank_i(d))`。k 是平滑参数，控制排名靠后的文档能获得多少分数。k 越大，尾部文档的分数越高。实验验证 k=5~60 之间 RRF 排序结果无显著差异，取中间值 30 保证可迁移性。
> 
> 选 RRF 而不是加权平均的原因：向量检索的 cosine 分数和 BM25 分数尺度不同（cosine 在 [0,1]，BM25 无上限），加权平均需要先做分数归一化，引入了额外的偏差。RRF 只看排名不看分数，天然对分数尺度鲁棒。

**代码** (`app/tools/llamaindex_tools.py:348-365`)：
```python
fused = []
for i, n in enumerate(nodes):
    vector_rank = i + 1
    try:
        bm25_rank = bm25_rank_args.index(i) + 1
    except ValueError:
        bm25_rank = len(nodes)
    rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)
    fused.append((n, rrf_score))
```

**Hook 3："34 条 ground-truth" → 会问数据来源和可信度**

预期追问：Q16 见前文。关键要点：
- 论文是模拟的，但评测框架和方法论真实
- 数据完全可复现（`scripts/generate_papers.py` + `app/evaluation/evaluate.py`）
- 第一次评测发现天花板效应 → 扩库到 90 篇 → 获得有区分度的结果 → 这个迭代过程本身就是工程能力的体现

**Hook 4："MRR 0.97" → 会问为什么不是 1.0**

> 0.97 意味着大多数 query 的目标文档排在第一位，但不是全部。失败的 case 主要是跨主题对比 query——比如"Compare RAG and FiD for open-domain QA"，两篇目标论文在 embedding 空间中的距离较远，BM25 也只能匹配到关键词重叠较多的那篇。这是 hybrid 检索的自然瓶颈，换成更大的 embedding 模型（如 text-embedding-3-large）可能进一步缩小差距。

### 7.4 子弹 3 深度拆解：证据结构化沉淀

**简历原文**：
> 将检索证据依次整理为证据记录、论文卡片（含问题/方法/实验/结论/局限性）、横向对比矩阵和 Markdown 综述初稿，形成"检索 → 整理 → 对比 → 撰写"的材料整理闭环。

**Hook 1："证据记录 → 论文卡片 → 对比矩阵 → Markdown" → 会问信息抽取怎么做**

预期追问："证据分类是关键词匹配还是模型驱动？为什么选关键词匹配？"

> 基于关键词匹配，不是 NER 也不是文本分类模型。代码在 `app/services/paper_card_service.py`：
> ```python
> FIELD_KEYWORDS = {
>     "method": ("method", "approach", "model", "framework", "算法", "方法"...),
>     "experiment": ("experiment", "dataset", "benchmark", "实验", "数据集"...),
>     ...
> }
> ```
> 
> 选择关键词匹配的原因：1）不需要训练数据；2）结果确定性强，可调试——出错了能精确知道为什么；3）在证据片段上效果足够。代价是泛化性差——"unknown term"无法匹配。后续可以升级到 LLM-as-a-Judge 做语义分类。

**Hook 2："卡片 ID 用 SHA256" → 会问为什么不是 UUID**

> SHA256 摘要前 16 位作为 card_id，具有**确定性**——相同证据组合产出相同 card_id，避免重复提交导致重复卡片。UUID 每次生成不同，需要额外去重逻辑。代码：`app/services/paper_card_service.py:120`：
> ```python
> digest_raw = "|".join([title, source, *evidence_ids, *quotes])
> card_id = hashlib.sha256(digest_raw.encode()).hexdigest()[:16]
> ```

### 7.5 子弹 4 深度拆解：工程化质量保障

**简历原文**：
> 补充 API Key 鉴权、四层 SQL 注入纵深防护（前缀白名单 + 多语句拦截 + 关键字黑名单 + 表名白名单）、文件上传三层校验（类型/大小/数量）、ContextVar 会话隔离与任务超时保护（300s）；配套 255 项测试覆盖核心模块，支持三种 embedding 模式（mock/local/openai）与可插拔检索策略配置，降低部署与调试门槛。

**Hook 1："四层 SQL 注入纵深防护" → 最可能被深挖的部分**

预期追问 1："说说每一层的原理和绕过可能？"

> 四层防护在 `app/tools/db_tools.py:79-96`：
> ```python
> def _validate_readonly_sql(query: str) -> tuple[bool, str]:
>     cleaned = _strip_sql_comments(query)        # 先清注释
>     if ";" in cleaned:                           # 层2: 多语句拦截
>         return False, "拒绝执行：不允许多语句 SQL"
>     if not sql_upper.startswith(READ_ONLY_PREFIXES):  # 层1: 前缀白名单
>         return False, "拒绝执行：只允许 SELECT/SHOW/DESCRIBE/EXPLAIN 查询"
>     tokens = set(re.findall(r"\b[A-Z_]+\b", sql_upper))  # 层3: 关键字黑名单
>     if forbidden := sorted(tokens & FORBIDDEN_SQL_WORDS):
>         return False, f"包含非只读关键字 {', '.join(forbidden)}"
>     return True, cleaned
> ```
> 
> 层1（前缀白名单）只允许 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH 开头。绕过可能：`/**/SELECT` 注释前缀——但注释处理 `_strip_sql_comments` 先清除注释。MySQL 的 `/*!SELECT*/` 语法——`TRADITIONAL` SQL mode 使这种语法失效。
> 
> 层2（多语句拦截）检查分号。绕过可能：无分号的 UNION 注入——进入层3检测。
> 
> 层3（关键字黑名单）正则提取 SQL 关键字。绕过可能：`DRO/**/P` 注释插入——注释已提前清除。编码绕过——检测前已做 upper()。
> 
> 层4（表名白名单）在 `get_table_data` 和 `list_sql_tables` 中检查——不在预设列表中的表名直接拒绝。
> 
> 真正的兜底是数据库权限——MySQL 用只读用户连接，SQLite 用 `PRAGMA query_only=ON`。即使代码层校验被绕过，数据库层也会拒绝写入。

预期追问 2："注释清理的正则够吗？嵌套注释呢？"

> `_strip_sql_comments` 先清 `/* */` 块注释（`re.DOTALL`），再清 `--` 和 `#` 行注释。多级嵌套注释是 SQL 标准禁止的，MySQL 也不支持。但注意 `_strip_sql_comments` 只能处理标准注释，不能处理 `/*!MySQL-specific*/` 这种——不过 `TRADITIONAL` SQL mode 已禁用了这个语法。

**Hook 2："ContextVar 会话隔离" → 会问和 threading.local 的区别**

预期追问："为什么要用 ContextVar 不是 threading.local？"

> 因为 `asyncio` 是单线程并发。多个协程在同一个线程中切换——`threading.local` 绑定的是线程，不区分同一线程中的不同协程，数据会"串台"。`ContextVar` 绑定的是"上下文"，随 `await` 自动传播到子协程。
> 
> 代码在 `app/api/context.py`：
> ```python
> _session_dir_ctx: ContextVar[Optional[str]] = ContextVar("session_dir", default=None)
> _thread_id_ctx: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)
> 
> def set_session_context(path: str) -> Token[Optional[str]]:
>     return _session_dir_ctx.set(path)
> 
> def get_session_context() -> Optional[str]:
>     return _session_dir_ctx.get()
> 
> def reset_session_context(session_token, thread_token=None):
>     _session_dir_ctx.reset(session_token)
> ```

使用方式——在 `main_agent.py:82-83`：
```python
session_dir_token = set_session_context(session_dir_str)
session_id_token = set_thread_context(session_id)
try:
    # ... 执行 Agent ...
finally:
    reset_session_context(session_dir_token, session_id_token)
```

**Hook 3："255 项测试" → 会问测试策略**

预期追问："测试覆盖率 70%，剩下的 30% 为什么不测？"

> 剩余 30% 主要是三类不适用单元测试的模块：1）需要真实外部模型（llamaindex_tools 的 embedding、rerank_tools 的 MiniLM）；2）需要真实数据库连接（db_tools 的 MySQL）；3）需要完整 DeepAgents 运行时（main_agent）。这些应该由集成/端到端测试覆盖——mock 掉外部依赖的单元测试虽然在覆盖率上好看，但测试价值很低（测的都是 mock 行为，不是真实行为）。

预期追问 2："最重要的测试是哪些？"

> 三种最重要的测试：1）SQL 注入防护测试（18 个）——安全底线，覆盖常见注入手法包括 UNION、分号、注释绕过、编码绕过等；2）测试隔离验证——确保 255 个测试可以任意顺序执行不互相影响；3）论文卡片服务测试（11 个，100% 覆盖率）——核心业务逻辑。

**Hook 4："三种 embedding 模式" → 会问设计模式**

> 策略模式（Strategy Pattern）。`app/tools/llamaindex_tools.py` 的 `_configure_embedding()` 函数根据 `LLAMAINDEX_EMBED_MODEL` 环境变量选择实现：
> - **mock**：`MockEmbedding(384)` 随机向量，用于流程测试
> - **local**：`HuggingFaceEmbedding(all-MiniLM-L6-v2)` 本地模型
> - **openai**：`OpenAIEmbedding(text-embedding-3-small)` API 调用
> 
> 通过 `ALLOW_MOCK_EMBEDDING=true` 控制降级行为。这种设计让新开发者从 mock 模式快速上手，不需要下载模型或配置 API Key 就能跑通全流程。

### 7.6 参数设计总表

| 参数 | 值 | 所在文件 | 选择依据 |
|------|-----|---------|---------|
| `rrf_k` | 30 | `retrieval_config.py` | k=5~60 实验无显著差异，取中间值。越大尾部文档分数越高 |
| `candidate_multiplier` | 2 | `retrieval_config.py` | mult=2 与 3 无差异，节省 33% 计算量 |
| `final_top_k` | 5 | `retrieval_config.py` | Recall 与延迟的平衡点，大多数 query 5 篇够用 |
| `enable_reranker` | False | `retrieval_config.py` | 延迟 13s + 实测降低 Recall，默认关闭 |
| `chunk_size` | 512 | `llamaindex_tools.py` | 学术论文章节典型长度 |
| `chunk_overlap` | 64 | `llamaindex_tools.py` | 12.5% 重叠，保证跨 chunk 信息不丢失 |
| `VERIFIED_THRESHOLD` | 0.5 | `citation_checker.py` | 保守策略，宁可漏标不可误标 |
| `LOW_CONFIDENCE_THRESHOLD` | 0.25 | `citation_checker.py` | 低置信度阈值 |
| `AGENT_TASK_TIMEOUT_SECONDS` | 300 | `server.py` | Agent 任务典型 30-120s，300s 是安全边界 |
| `RATE_LIMIT_PER_MINUTE` | 60 | `server.py` | 单一 IP 限流，防止打满 |
| `Semaphore` 并发数 | 4 | `server.py` | 防止 GPU/OOM，I/O 密集型可适当提高 |
| `MAX_UPLOAD_BYTES` | 20MB | `server.py` | 单文件限制，防止内存溢出 |
| `bm25_tokenizer` | None (split) | `retrieval_config.py` | 英文论文 split 优于 jieba，中文时切换 jieba |

### 7.7 关键代码路径速查

面试中被问到"具体在哪实现"时快速回答：

| 功能 | 文件 | 关键行 |
|------|------|--------|
| 主 Agent 组装 | `app/agent/main_agent.py` | L38 `create_deep_agent(...)` |
| Agent 异步执行 | `app/agent/main_agent.py` | L129 `async for chunk in main_agent.astream(...)` |
| 向量+BM25+RRF 融合检索 | `app/tools/llamaindex_tools.py` | L313 `_retrieve_nodes()` |
| RRF 分数计算 | `app/tools/llamaindex_tools.py` | L355 循环体 |
| ContextVar 上下文 | `app/api/context.py` | L13-L18 |
| WebSocket 连接管理 | `app/api/monitor.py` | ConnectionManager class |
| 事件三路输出 | `app/api/monitor.py` | `_emit()` 方法 |
| SQL 注入防护 | `app/tools/db_tools.py` | L79 `_validate_readonly_sql()` |
| 论文卡片构建 | `app/services/paper_card_service.py` | L107 `build_paper_card_from_evidence()` |
| 引用校验 | `app/tools/citation_checker.py` | L112 `verify_citations()` |
| 检索配置 | `app/config/retrieval_config.py` | 全文件 |
| Eval 评测 | `app/evaluation/evaluate.py` | 全文件 |
| Embedding 策略 | `app/tools/llamaindex_tools.py` | L75 `_configure_embedding()` |

### 7.8 常见 Hook 一句话应答

面试官提到以下关键词时，一句话切入：

- **"LangChain"** → "我用 DeepAgents 不是因为 LangChain 不好，而是需要 EventStream 的可观测性——每一步 tool_call 的输入输出我都要看到"
- **"Perplexity"** → "区别是我们自托管，论文库私有，搜索源可控。Perplexity 不能指定搜 Google Scholar"
- **"ChatPDF"** → "我们不只是读一篇论文，我们做多论文交叉分析和引文校验"
- **"单例"** → "ToolMonitor 用 `__new__` 实现单例，确保所有模块共享同一个 `_emit` 方法"
- **"mock"** → "三种 embedding 模式的设计是为了降低调试门槛——mock 模式不需要任何模型就能跑通全流程"
- **"eval 天花板"** → "第一次评测所有策略 MRR 都 0.95+，根本拉不开差距。扩到 90 篇论文后才看到 BM25+RRF 的真正价值"
- **"测试隔离"** → "最大的教训——`importlib.reload` 不恢复环境变量导致 20 个测试全挂。现在所有改全局状态的代码都有对称的恢复接口"
- **"__new__"** → "用来做 ToolMonitor 的单例，确保全局只有一个监控实例"

---

## 8. 系统架构分类总览

> 从架构分类的角度，将项目拆解为 8 个核心领域。每个领域包含：涉及模块、技术选型理由、设计方案、核心代码、量化结果、面试亮点。适合面试前系统性地过一遍"项目到底有哪些东西"。

```
┌────────────────────────────────────────────────────────────┐
│                   DeepSearch Agents                         │
├────────────┬──────────┬───────────┬───────────┬────────────┤
│ Agent编排  │ 检索排序  │ 数据持久化 │ API实时通 │  安全防护   │
│ DeepAgents │ LlamaIdx │ SQLite   │ 信         │ SQL注入防护 │
│ LangGraph   │ BM25     │ WAL       │ FastAPI    │ 路径校验   │
│ Orchestrator│ RRF      │ MySQL     │ WebSocket  │ 文件校验   │
│ -Workers    │ MiniLM   │ Memory    │ ContextVar │ API Key    │
├────────────┴──────────┴───────────┴───────────┴────────────┤
│  证据处理与报告        测试与评测            部署与配置        │
│  论文卡片构建          255项测试             Docker Compose   │
│  对比矩阵              Eval评测              Nginx反向代理    │
│  综述报告              3策略A/B对比          4容器编排         │
│  引用校验                                              │
└────────────────────────────────────────────────────────────┘
```

### 8.1 智能体编排层 (Agent Orchestration)

**概述**：基于 DeepAgents + LangGraph 构建的一主三从多智能体系统。主智能体负责任务规划、子智能体调度和综述生成；三个子智能体各自负责单一信息源（网络搜索、论文知识库、结构化数据库）。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/agent/main_agent.py` | 主智能体组装（`create_deep_agent`）+ 异步执行入口（`run_deep_agent`） |
| `app/agent/subagents/network_search_agent.py` | 网络搜索子智能体（SearXNG） |
| `app/agent/subagents/paper_knowledge_agent.py` | 论文知识库子智能体（LlamaIndex） |
| `app/agent/subagents/database_query_agent.py` | 数据库查询子智能体（MySQL） |
| `app/agent/prompts.py` | 提示词 YAML 加载 |
| `app/agent/llm.py` | OpenAI 兼容模型初始化 |
| `app/prompt/prompts.yml` | 提示词配置（主智能体 + 子智能体） |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| AI 框架 | DeepAgents 0.5.7 | LangChain AgentExecutor | EventStream 模式暴露每一步 tool_call 输入输出，AgentExecutor 内部隐式重试/回退太多，无法精确定位问题 |
| 状态管理 | LangGraph StateGraph | 自研状态机 | LangGraph 提供 checkpoint、interrupt、astream 等原生能力，减少重复开发 |
| 记忆系统 | LangGraph InMemorySaver | SQLite / Redis | 会话级记忆，不需要持久化到磁盘；每个任务独立 thread_id |
| 子智能体注入 | subagents 参数 | 手动嵌套 AgentExecutor | DeepAgents 将子智能体封装为 tool 暴露给主智能体，调用链清晰可追踪 |

**设计方案**：

1. **Orchestrator-Workers 模式**：主智能体（Orchestrator）负责任务分解→调度→汇总，子智能体（Workers）各自专注单一数据源。主智能体不直接调用搜索/数据库工具，而是通过 subagents 参数委托给子智能体。

2. **工具与子智能体职责分离**：
   - 主智能体 tools：`generate_markdown`、`convert_md_to_pdf`、`read_file_content`（文件产出类）
   - 子智能体内 tools：`internet_search`、`execute_sql_query`、`search_paper_library`（数据获取类）

3. **提示词驱动调度**：主智能体的 system_prompt 通过自然语言描述"什么情况调哪个子智能体"，不是硬编码规则。是模型理解 prompt 后的自主决策，但受 prompt 边界约束。

4. **ContextVar 会话隔离**：每个 `run_deep_agent()` 调用在开始时 `set_session_context()`，结束时 `reset_session_context()`，保证并发执行时目录和数据不串台。

**核心代码** (`app/agent/main_agent.py:38-44`)：
```python
main_agent = create_deep_agent(
    model=model,
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)
```

异步执行 (`main_agent.py:129-157`)：
```python
async for chunk in main_agent.astream(
    {"messages": [{"role": "user", "content": task_query + path_instruction}]},
    config=config,
):
    for node_name, state in chunk.items():
        if not state or "messages" not in state:
            continue
        messages = state["messages"]
        if messages and isinstance(messages, list):
            last_msg = messages[-1]
            if node_name == "model":
                if last_msg.tool_calls:
                    # 检测到子智能体调用 → 推送 assistant_call 事件
                    for tool_call in last_msg.tool_calls:
                        if tool_call["name"] == "task":
                            monitor.report_assistant(...)
                elif last_msg.content:
                    # 主智能体产生最终结果 → 推送 task_result
                    monitor.report_task_result(last_msg.content)
```

**设计结果**：
- 1 主 + 3 从的清晰分工，每个子智能体专注单一数据源
- 工具调用日志完整记录到 `tool_calls.log`，按 thread_id 可追溯
- WebSocket 实时推送每一步决策（tool_start / assistant_call / task_result）

**面试亮点**：
> "我选 DeepAgents 不是因为 LangChain 不好，而是 EventStream 模式的可观测性。AgentExecutor 内部自动重试、自动解析输出——这些隐式行为在调试时是黑盒。EventStream 把每一步 tool_call 的输入输出暴露为结构化事件，我可以精确追踪到底哪一步出了错。这在学术检索这种对精度要求高的场景里至关重要。"


### 8.2 检索与排序层 (Retrieval & Ranking)

**概述**：基于 LlamaIndex 构建的本地论文检索流水线，支持向量语义检索 + BM25 关键词精确匹配 + RRF 无参数融合 + 可选 MiniLM 重排序。嵌入策略支持 mock/local/openai 三种模式切换。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/tools/llamaindex_tools.py` | 索引构建、向量检索、BM25+RRF 融合、证据格式化（~500 行核心逻辑） |
| `app/tools/rerank_tools.py` | MiniLM cross-encoder 重排序（默认关闭） |
| `app/config/retrieval_config.py` | 检索参数集中配置（rrf_k、candidate_multiplier、final_top_k） |
| `app/evaluation/evaluate.py` | 检索评测脚本（34 条 query、3 策略 A/B 对比） |
| `app/config/paths.py` | 目录配置（PAPER_DIR、INDEX_DIR、MODEL_CACHE_DIR） |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| 检索框架 | LlamaIndex | 裸 LangChain / 自研 | 开箱即用的文档解析、分块、索引持久化 |
| 语义检索 | all-MiniLM-L6-v2 (384维) | text-embedding-3-large (3072维) | 离线部署、本地加载、免 API 调用 |
| 关键词检索 | BM25 (rank_bm25) | Elasticsearch | 轻量、在候选集上计算（非全库），无运维成本 |
| 融合策略 | RRF (k=30) | 加权平均 / Learning to Rank | 零参数、对分数尺度鲁棒；LTR 需要标注数据 |
| 分块策略 | SentenceSplitter (512/64) | RecursiveCharacterTextSplitter | 语义完整的句子级分块，适合论文文本 |

**设计方案**：

1. **级联剪枝策略**：
   ```
   全库 → 向量检索 (candidate_multiplier=2, 最大20候选)
        → BM25 在同一候选集上计算精确匹配分数
        → RRF 融合两个排序 (不看分数只看排名)
        → [可选] MiniLM cross-encoder 重排序
        → Top-K 最终结果 (final_top_k=5)
   ```
   BM25 不在全库上计算（太慢），而是在向量检索的候选集上计算——这是级联剪枝的关键设计。

2. **策略模式 Embedding** (`app/tools/llamaindex_tools.py:75-128`)：
   ```python
   def _configure_embedding(imports):
       mode = os.getenv("LLAMAINDEX_EMBED_MODEL", "mock").lower()
       if mode == "openai":
           Settings.embed_model = OpenAIEmbedding(...)
       elif mode == "local":
           Settings.embed_model = HuggingFaceEmbedding(...)
       else:
           Settings.embed_model = MockEmbedding(embed_dim=384)
   ```
   mock 模式用随机向量调试流水线，local 模式离线运行，openai 模式调 API 获取高维 embedding。

3. **RRF 融合** (`llamaindex_tools.py:348-365`)：
   ```python
   k = cfg["rrf_k"]  # 30
   bm25_rank_args = sorted(range(len(bm25_scores)), key=lambda j: bm25_scores[j], reverse=True)
   fused = []
   for i, n in enumerate(nodes):
       vector_rank = i + 1
       try:
           bm25_rank = bm25_rank_args.index(i) + 1
       except ValueError:
           bm25_rank = len(nodes)  # BM25 未匹配 → 最低排名
       rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)
       fused.append((n, rrf_score))
   fused.sort(key=lambda x: x[1], reverse=True)
   ```

4. **索引变更检测**：`_manifest()` 基于文件列表 + embedding 配置 + chunk 参数生成 SHA256 摘要。换 embedding 模型或 chunk 参数时自动重建索引，避免旧索引与新配置不匹配。

5. **BM25 降级兜底**：当 BM25 max score < 0.1（query 全是未见过的词）时，跳过 RRF 融合，直接返回向量检索结果。

**核心代码 - 索引构建** (`llamaindex_tools.py:200-236`)：
```python
def _load_or_build_index():
    _configure_embedding(imports)
    if _index_is_current(current_manifest):
        return load_index_from_storage(storage_context)
    # 全量重建
    documents = SimpleDirectoryReader(input_dir=str(PAPER_DIR), ...).load_data()
    parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = parser.get_nodes_from_documents(documents)
    index = VectorStoreIndex(nodes)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    _save_manifest(current_manifest)
    return index
```

**设计结果**：

| 策略 | Recall@3 | MRR | 相对提升 |
|------|----------|-----|----------|
| 纯向量（baseline） | 0.8775 | 0.8824 | — |
| **混合 BM25+RRF** | **0.9534** | **0.9706** | **+10% MRR** |
| 全链路（+MiniLM） | 0.8309 | 0.8676 | -1.7% MRR |

**面试亮点**：
> "最大的发现是 MiniLM 重排序实际上降低了效果——MRR 从 0.97 掉到 0.87，因为重排序把候选集从 20 压缩到 10，丢失了正确文档。这意味着在本论文库规模下，BM25+RRF 已经足够好。这也验证了一个原则：'加一层模型'不等于'效果更好'，必须用数据验证每个设计决策。"

> "评测方法论上最大的教训是天花板效应。一开始 17 篇论文时所有策略 MRR 都在 0.95 以上，完全拉不开差距。扩到 90 篇后才看到真实差异。所以'有评测'不等于'有区分度的评测'——评测集的难度和规模决定了你能从中获得多少信息。"


### 8.3 数据持久化层 (Data Persistence)

**概述**：双数据库架构——SQLite WAL 存储会话、事件、证据、记忆等应用内部状态；MySQL 8.4 存储论文元数据（仅教学演示）。三层数据隔离（user_id + workspace_id + thread_id）。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/models/session.py` | SQLite 数据模型（会话、运行事件、证据记录、论文卡片、引用校验） |
| `app/memory/memory_store.py` | 跨会话长期记忆（关键词匹配检索） |
| `app/tools/db_tools.py` | MySQL 连接管理 + 只读查询工具 |
| `docker/docker-compose.yaml` | MySQL 8.4 容器配置 |
| `docker/mysql/mysql.sql` | 论文元数据教学数据 |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| 应用数据库 | SQLite WAL | JSON 文件 | 并发安全（WAL 支持多读一写）、结构化查询、事务原子性 |
| 论文元数据 | MySQL 8.4 | 统一 SQLite | 演示多数据源集成，展示 Agent 调用结构化数据库的能力 |
| 事务模式 | BEGIN IMMEDIATE | BEGIN DEFERRED | 高并发写时 DEFERRED 导致 SQLITE_BUSY，IMMEDIATE 立即拿锁 |
| ORM | 原生 sqlite3 | SQLAlchemy | 项目规模小，不需要 ORM 抽象层 |

**设计方案**：

1. **SQLite WAL 并发模型**：
   - WAL（Write-Ahead Logging）模式下，读事务不阻塞写事务，写事务不阻塞读事务
   - 多个读事务可以同时进行，单个写事务串行
   - `BEGIN IMMEDIATE` 在事务启动时就获取写锁，避免写到一半才撞锁

2. **三层数据隔离**：所有表包含 `user_id`、`workspace_id`、`thread_id` 三个隔离字段。当前版本 `user_id` 和 `workspace_id` 为占位符，为多租户预留扩展点。

3. **记忆系统** (`app/memory/memory_store.py`)：基于关键词子串匹配的轻量跨会话记忆，不引入向量检索。词级重叠率检测（threshold=0.5）判断是否需要覆盖保存。

4. **会话流程**：
   ```
   任务开始 → save_session() 创建会话记录
            → search(keyword) 检索历史记忆 → 注入 system prompt
   任务结束 → 取最终回答前500字 → save(key, content, session_id)
            → update_session() 更新状态
   ```

**核心代码 - BEGIN IMMEDIATE**：
```python
conn = sqlite3.connect(path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("BEGIN IMMEDIATE")
# ... 执行写入操作 ...
conn.commit()
```

**设计结果**：
- 并发安全：多个 Agent 同时写入事件日志不会冲突
- 查询能力：按 thread_id、event_type、时间戳做结构化过滤
- 一致性：原子写入保证事件不丢失、不部分写入

**面试亮点**：
> "JSON 文件在多用户并发写时存在竞态条件——两个任务同时写入会互相覆盖。SQLite WAL 解决这个问题的同时保持了零配置的优势。关键细节是 `BEGIN IMMEDIATE`——SQLite 默认的 `BEGIN` 是 DEFERRED 的，在高并发写时容易撞上 `SQLITE_BUSY`，写了半截才发现冲突必须回滚。IMMEDIATE 一进事务就声明写意向，要么成功要么阻塞，不会写到一半才失败。"

> "双数据库不是炫技——SQLite 存应用状态（会话、事件），MySQL 存论文元数据，两者数据特性不同。SQLite 无服务器适合单机，MySQL 支持并发查询适合共享知识库。按数据特性选择存储，而不是一刀切。"


### 8.4 API 与实时通信层 (API & Realtime)

**概述**：FastAPI 提供 REST API 和 WebSocket 端点。异步 Agent 任务通过 asyncio.Task 调度，执行过程和结果通过 WebSocket 实时推送，同时持久化到 SQLite。断线重连后可从 SQLite 拉取历史事件补全展示。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/api/server.py` | 全部 REST 端点 + WebSocket 端点 + 异步任务管理 |
| `app/api/monitor.py` | ToolMonitor（事件三路输出）+ ConnectionManager（WebSocket 连接管理） |
| `app/api/context.py` | ContextVar 会话/线程隔离 |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| Web 框架 | FastAPI + Uvicorn | Flask | 需要原生 async/WebSocket 支持 |
| 实时推送 | WebSocket | SSE / 轮询 | 全双工、低延迟、前端可发送取消指令 |
| 并发模型 | asyncio 协程 | 多线程 | I/O 密集型场景，协程开销远小于线程 |
| 会话隔离 | ContextVar | threading.local | asyncio 单线程并发需要上下文感知的隔离机制 |

**设计方案**：

1. **异步任务调度**：`POST /api/task` 创建 `asyncio.create_task()` 在后台运行 Agent，立即返回 `{"status": "started", "thread_id": ...}`。`active_tasks` 字典维护 thread_id → Task 的映射。

2. **三路事件输出** (`monitor.py:40-106`)：
   ```
   _emit() 方法
     ├── WebSocket 推送 → ConnectionManager.send_to_thread() → 前端实时展示
     ├── SQLite 持久化 → save_run_event() → 断线重连后历史拉取
     └── 控制台输出 → print() → 脚本调试场景
     └── 日志文件 → tool_calls.log → 审计追踪
   ```

3. **WebSocket 生命周期管理**：
   - `ConnectionManager` 以 `thread_id → WebSocket` 字典维护连接
   - `lifespan` 事件绑定事件循环（`manager.set_loop(loop)`）
   - 跨线程协程投递：`asyncio.run_coroutine_threadsafe()` 确保从非主协程也能发送 WebSocket 消息
   - 断线 → `WebSocketDisconnect` 触发清理 → Agent 继续运行
   - 重连 → 新建 WS 连接 → `GET /api/task/{id}/events` 拉取历史

4. **ContextVar 传播机制**：
   ```python
   # app/api/context.py
   _session_dir_ctx: ContextVar[Optional[str]] = ContextVar("session_dir", default=None)
   _thread_id_ctx: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)
   ```
   在 `run_deep_agent()` 入口 set，子协程通过 `get()` 获取。随 `await` 自动传播。

**核心代码 - 事件循环绑定** (`server.py:53-59`)：
```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)
    yield
```

**核心代码 - 跨线程 WebSocket 投递** (`monitor.py:108-129`)：
```python
def _send_to_websocket(self, payload, thread_id, manager_loop):
    coroutine = self.websocket_manager.send_to_thread(payload, thread_id)
    if current_loop == manager_loop:
        current_loop.create_task(coroutine)      # 同一循环 → 直接 create_task
    else:
        asyncio.run_coroutine_threadsafe(coroutine, manager_loop)  # 跨线程 → 线程安全投递
```

**设计结果**：
- API 响应 < 10ms（不含 Agent 执行时间）
- WebSocket 事件延迟 < 100ms
- 断线重连可拉取 SQLite 历史事件完整恢复前端状态
- Semaphore(4) 防止并发 Agent 耗尽资源

**面试亮点**：
> "WebSocket 断连和 Agent 执行是完全解耦的——`active_tasks` 存的是 `asyncio.Task` 对象，WS 连接只是事件输出通道之一。用户刷新页面后重新连接 WebSocket，通过 `GET /api/task/{id}/events` 拉取 SQLite 里的事件历史，然后继续接收实时推送。核心设计思路：WebSocket 负责实时，SQLite 负责持久化，两者独立。"

> "ContextVar 的坑在于：很多人以为 `threading.local` 能在 asyncio 中工作，但实际上 asyncio 是单线程并发，多个协程切换时 `threading.local` 不区分它们，数据会'串台'。ContextVar 绑定的是协程上下文而非线程，随 await 自动传播。这是 Python 3.7 引入的特性，专门解决异步场景的上下文隔离问题。"


### 8.5 安全防护层 (Security)

**概述**：纵深防御设计——四层 SQL 注入防护、路径穿越防护、文件上传三层校验、API Key 认证。每层独立工作，上层被绕过时下层仍有兜底。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/tools/db_tools.py` | SQL 注入防护（`_validate_readonly_sql`）+ 只读配置 |
| `app/utils/path_utils.py` | 路径解析 + 防穿越（`resolve_path`） |
| `app/api/server.py` | API Key 中间件、文件上传校验、Rate Limiting |
| `app/api/context.py` | ContextVar 会话隔离（防目录串台） |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| SQL 防护策略 | 四层纵深防御 | 仅参数化查询 | LLM 生成的 SQL 不可控，需要多层校验而非单一防护 |
| 路径防护 | resolve() + is_relative_to() | 字符串前缀检查 | 字符串检查可被 `../` 绕过，`resolve()` 解析真实路径 |
| 认证方式 | API Key (Header) | JWT / OAuth | 轻量、无状态，适合 API 对 API 的服务场景 |

**设计方案**：

1. **四层 SQL 注入防护** (`db_tools.py:79-95`)：
   ```
   层1 - 前缀白名单: 只允许 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH 开头
   层2 - 多语句拦截: 拒绝包含分号 `;` 的语句
   层3 - 关键字黑名单: 拦截 DDL (DROP/ALTER/CREATE) 和 DML (INSERT/UPDATE/DELETE)
   层4 - 表名白名单: 只允许操作预设表名
   兜底 - 数据库权限: MySQL 只读用户 + SQLite PRAGMA query_only=ON
   ```

2. **SQL 注释预处理** (`db_tools.py:72-76`)：
   ```python
   def _strip_sql_comments(query: str) -> str:
       query = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)  # 块注释
       query = re.sub(r"--[^\n\r]*", " ", query)              # 行注释 --
       query = re.sub(r"#[^\n\r]*", " ", query)               # 行注释 #
       return query.strip()
   ```
   先清注释再校验，防止 `/**/SELECT`、`DRO/**/P` 等绕过手法。

3. **路径穿越防护**：`resolve_path()` 使用 `Path.resolve()` 获取真实路径，再通过 `is_relative_to()` 检查是否在允许目录下。`resolve()` 会解析 `..` 和符号链接，比字符串前缀检查安全得多。

4. **文件上传校验**：
   - 类型白名单：`.pdf`、`.md`、`.txt`、`.docx`、`.xlsx`、`.xls`
   - 大小限制：`MAX_UPLOAD_BYTES=20MB`
   - 数量限制：`MAX_UPLOAD_FILES=5`

5. **API Key 认证** (`server.py:64-70`)：
   ```python
   API_KEY = os.getenv("API_KEY", "").strip()
   ALLOWED_API_KEYS: set[str] = set()
   if API_KEY:
       ALLOWED_API_KEYS.add(API_KEY)
   DISABLE_AUTH = os.getenv("DISABLE_API_AUTH", "false").lower() == "true"
   ```
   支持多个 API Key 扩展，`DISABLE_API_AUTH=true` 可在开发环境跳过认证。

**设计结果**：
- 18 个专门的 SQL 注入测试覆盖常见注入手法，全部拦截
- 12 个路径穿越测试覆盖 `../`、编码绕过等
- 255 个测试全通过，安全相关测试是回归测试的重中之重

**面试亮点**：
> "SQL 注入防护不是某一层就能搞定的。LLM 生成的 SQL 充满不确定性——可能正常 SELECT 里夹带 UNION 注入，也可能合法语句包含 DROP 关键字。四层纵深防御中每一层独立工作，即使注释预处理被绕过，关键字黑名单也能兜底；即使代码层校验全被绕过，数据库层的只读用户和 PRAGMA query_only 也会拒绝写入。真正的兜底是数据库权限，不是代码。"

> "路径穿越不只用字符串检查，因为 `Path('../etc/passwd').resolve()` 解析出的真实路径可能看起来像个合法路径。`is_relative_to()` 确保路径确实在目标目录下——这是 Python 3.9 引入的标准库方法，比手动检查 `/` 或 `..` 更可靠。"


### 8.6 证据处理与报告生成 (Evidence & Reports)

**概述**：从检索结果到结构化综述的完整沉淀管线——证据记录 → 论文卡片（5字段分类）→ 横向对比矩阵 → Markdown 综述初稿。引用校验模块自动检测 claim 与证据的匹配度。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `app/services/paper_card_service.py` | 论文卡片构建（关键词分类 + SHA256 ID） |
| `app/services/paper_matrix_service.py` | 多论文横向对比矩阵 |
| `app/services/review_report_service.py` | Markdown 综述报告生成 |
| `app/tools/citation_checker.py` | 引用校验（MiniLM 语义相似度） |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| 证据分类 | 关键词匹配 | NER / 文本分类模型 | 确定性强、无训练成本、易调试 |
| 卡片 ID | SHA256 前16位 | UUID | 确定性去重——相同证据产出相同 ID |
| 引用校验 | MiniLM cosine similarity | LLM-as-a-Judge | 轻量、可离线、延迟低 |

**设计方案**：

1. **证据沉淀管线**：
   ```
   检索证据 (EvidenceRecord)
       → 论文卡片 (PaperCard) — 按 problem/method/experiment/conclusion/limitation 5字段分类
       → 对比矩阵 (PaperMatrix) — 多论文横向比较
       → 综述初稿 (Markdown) — 自动生成带引用的结构化文档
       → 引用校验 (CitationCheck) — verified / low_confidence / unfounded 三级
   ```

2. **关键词分类** (`paper_card_service.py:7-58`)：
   ```python
   FIELD_KEYWORDS = {
       "problem": ("problem", "challenge", "motivation", "研究问题", ...),
       "method": ("method", "approach", "model", "framework", "方法", ...),
       "experiment": ("experiment", "dataset", "benchmark", "实验", ...),
       "conclusion": ("result", "outperform", "improve", "结论", ...),
       "limitation": ("limitation", "future work", "fail", "局限", ...),
   }
   ```
   在 evidence quote 文本中做子串匹配。未匹配任何字段的归入 "summary"。每类最多保留 2 条 excerpt，每条 ≤360 字。

3. **确定性去重** (`paper_card_service.py:112-120`)：
   ```python
   digest_raw = "|".join([
       clean_title, source,
       *[str(item.get("evidence_id", "")) for item in evidence],
       *_quote(item)[:120] for item in evidence[:3],
   ])
   card_id = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()[:16]
   ```
   相同标题 + 证据组合 → 相同 card_id。避免重复调用时重复创建卡片。

4. **引用校验** (`citation_checker.py`)：
   - 提取综述中的 `【证据: xxx】` 和 `【来源: 标题, p.5】` 标记
   - 从 `evidence_records` 表匹配对应证据
   - MiniLM 计算 claim 与 quote 的余弦相似度
   - 阈值：≥0.5 = verified / 0.25~0.5 = low_confidence / <0.25 = unfounded
   - 结果写入 SQLite `citation_checks` 表

**设计结果**：
- 论文卡片构建覆盖率 100%（测试验证）
- 引用校验覆盖全部 claim，unfounded 标记提示人工核验
- SHA256 确定性去重——重复提交不会产生重复卡片

**面试亮点**：
> "证据分类为什么用关键词匹配而不是模型？三个原因：第一，不需要训练数据；第二，关键词匹配结果确定性强——出错了能精确知道为什么；第三，在已有的 evidence 片段上效果已经足够。代价是泛化性差——未知术语无法匹配。后续可以升级到 LLM-as-a-Judge 做语义分类。"

> "卡片 ID 用 SHA256 而不是 UUID——UUID 每次生成不一样，需要额外去重逻辑。SHA256 摘要前 16 位，相同输入产出相同输出，天然去重。这是一个小的设计细节，但面试官看到这个会认可你思考了幂等性。"


### 8.7 测试与评测体系 (Testing & Evaluation)

**概述**：三层测试架构（单元 → 集成 → 端到端），255 个测试覆盖 13 个模块，覆盖率 70%。检索评测基于 34 条 ground-truth query、90 篇论文、3 策略 A/B 对比。

**涉及模块**：
| 文件/目录 | 职责 |
|-----------|------|
| `tests/test_production_hardening.py` | 工程可靠性测试（SQL 注入、路径穿越、文件上传） |
| `tests/test_server.py` | API 路由测试（ASGITransport） |
| `tests/test_*.py` | 各模块单元/集成测试 |
| `app/evaluation/evaluate.py` | 检索评测脚本（3 策略对比） |
| `docs/papers/_ground_truth.json` | Ground-truth 标注数据集（34 条 query） |
| `pyproject.toml` | pytest + coverage 配置 |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| 测试框架 | pytest + monkeypatch | unittest.mock | fixture 自动集成，修改在 teardown 后自动恢复 |
| API 测试 | httpx.ASGITransport | requests | 不启动服务器即可测试 FastAPI 路由，更快更独立 |
| 覆盖率 | coverage.py | — | pytest-cov 插件集成 |
| Eval 评测 | 34 query, 3 策略 A/B | 单一策略 | 对比才能看出不同策略的真实贡献 |

**设计方案**：

1. **三层测试架构**：
   ```
   单元测试（最多）:
     ├── 纯函数测试（SQL guard、path_utils）
     ├── Mock 测试（rerank、tavily、db_tools config）
     └── 服务测试（paper_card 100%、matrix 100%、review 98%）

   集成测试（关键路径）:
     ├── FastAPI routes（ASGITransport）
     ├── SQLite session store（tmp_path 隔离）
     └── 工具调用（LangChain invoke）

   端到端测试（计划中）:
     ├── Docker Compose 全栈
     └── 真实 MySQL + SearXNG
   ```

2. **测试隔离设计**：所有改全局状态的 fixture 必须提供对称的恢复接口。`monkeypatch` 修改在 fixture teardown 时自动恢复。临时文件使用 `tmp_path`。

3. **检索评测设计**：
   - 34 条 ground-truth query，8 个 AI 主题簇（GNN、Transformer、RL、RAG、Few-shot、LLM Training、CV、Optimization）
   - 3 种难度：单篇精确匹配、多篇对比、跨主题综合
   - 3 策略对比：纯向量 / BM25+RRF 混合 / 全链路(+MiniLM)
   - 指标：Recall@3、Recall@5、Recall@10、MRR

**评测结果**：

| 策略 | Recall@3 | Recall@5 | Recall@10 | MRR |
|------|----------|----------|-----------|-----|
| 纯向量（baseline） | 0.8775 | 0.9412 | 0.9902 | 0.8824 |
| **混合 BM25+RRF** | **0.9534** | **0.9681** | **0.9902** | **0.9706** |
| 全链路（+MiniLM） | 0.8309 | 0.9069 | 0.9902 | 0.8676 |

**面试亮点**：
> "测试最大的挑战不是写测试，而是让测试互不干扰。一开始 128 个测试有 8 个持续失败——单独跑全过，全量跑就挂。排查发现三个根因：`importlib.reload` 不恢复环境变量、SQLite 路径改了没恢复、monkeypatch 打错了模块层级。模块级全局状态是测试的天敌，所有改全局状态的代码必须提供对称的恢复接口。"

> "评测方法论上最重要的一课：'有评测'不等于'有区分度的评测'。17 篇论文时所有策略 MRR 都在 0.95 以上——任何改动都看不出效果。扩到 90 篇论文后才拉开差距。花时间标注 ground truth 是第一步，验证评测集能区分不同策略才是关键。"


### 8.8 部署与配置层 (Deployment & Config)

**概述**：Docker Compose 编排 4 个容器（backend + frontend + MySQL + SearXNG），Nginx 反向代理。环境变量驱动配置，Docker volume 持久化数据，容器名 DNS 通信。

**涉及模块**：
| 文件 | 职责 |
|------|------|
| `docker/docker-compose.yaml` | 4 容器编排 + volume + 网络 |
| `docker/Dockerfile.backend` | 后端 Docker 镜像 |
| `docker/Dockerfile.frontend` | 前端 Nginx 镜像 |
| `docker/nginx.conf` | 反向代理配置 |
| `docker/mysql/mysql.sql` | MySQL 初始化教学数据 |
| `docker/searxng/settings.yml` | SearXNG 搜索引擎配置 |
| `app/config/paths.py` | 运行时目录统一配置（DATA_ROOT） |
| `app/config/retrieval_config.py` | 检索参数配置 |
| `.env` / `.env.example` | 环境变量模板 |

**技术选型**：

| 选项 | 选择 | 弃用 | 理由 |
|------|------|------|------|
| 容器编排 | Docker Compose | K8s / 自部署 | 单机场景足够，开发/演示一键启动 |
| 搜索后端 | SearXNG (自托管) | Tavily API | 零费用、聚合 70+ 引擎、隐私不泄露 |
| 反向代理 | Nginx | 直连后端端口 | 统一入口、静态文件服务、防止端口冲突 |
| 模型缓存 | 本地 volume | HuggingFace 默认目录 | 收敛到 data/model_cache，避免容器内权限问题 |

**设计方案**：

1. **网络拓扑**：
   ```
   deepsearch-net (bridge)
     ├── backend  :8000
     ├── frontend :80 → host:8081  (Nginx)
     ├── mysql    :3306 → host:3309
     └── searxng  :8080 → host:8888
   ```
   服务间通过容器名通信（`mysql:3306`、`searxng:8080`），与物理端口映射解耦。

2. **Volume 持久化**：
   ```yaml
   volumes:
     deepsearch_mysql_data:      # MySQL 数据持久化
     deepsearch_output:          # 会话产物持久化
     deepsearch_model_cache:     # HF 模型缓存
     deepsearch_storage:         # LlamaIndex 索引持久化
     searxng_data:               # SearXNG 配置持久化
   ```

3. **配置分层**：
   - 环境变量（.env）：数据库连接、API Key、超时时间、embedding 模式
   - 代码配置（`retrieval_config.py`）：RRF k、candidate_multiplier、rerank 开关
   - 分离原则：环境变量是部署相关的，代码配置是业务逻辑不变的

4. **DATA_ROOT 统一目录** (`app/config/paths.py`)：
   ```
   data/
     ├── uploads/        # 用户上传文件
     ├── reports/        # 生成报告
     ├── papers/         # 论文 PDF 库
     ├── paper_index/    # LlamaIndex 索引
     ├── model_cache/    # HuggingFace 模型缓存
     └── sessions.sqlite3  # SQLite 全量持久化
   ```
   所有运行时数据收敛到 `data/` 目录，Docker 部署时只需挂载这一个目录。

**设计结果**：
- 4 容器一键部署：`docker compose up -d`
- Docker 构建上下文从 500MB 降到 37MB（`.dockerignore` 过滤）
- 模型缓存持久化，重启不重复下载

**面试亮点**：
> "容器间通信用 `mysql:3306` 不是 `localhost:3307`——Docker 每个容器有自己的网络栈，`localhost` 指向自己而不是对方。Compose 自动创建桥接网络并注册容器名 DNS，backend 里写 `mysql:3306` 就能解析到 MySQL 容器。物理端口映射从 `3307` 改成 `3309` 都不需要改代码。"

> "DATA_ROOT 统一收敛解决了一个很隐晦的 bug：原版代码在三个地方写死了不同路径——`app/output`、`output/`、`/app/output`——容器部署时某些目录不存在导致文件写入失败。全部收敛到 `data/` 后，Docker 只需要挂载这一个 volume，所有模块读写路径都是一致的。"

---

*生成时间：2026-07-01 | 此文档用于面试准备，结合简历中的项目描述回答效果更佳*
