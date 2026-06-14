# 面试技术详解：深度研搜多智能体系统

> 本文档围绕简历描述逐条拆解实现细节、核心 API 调用和面试应答要点。

---

## 一、总体架构回顾

```
用户 (React + Vite)
  │  POST /api/task  │  WS /ws/{thread_id}
  ▼                  ▼
FastAPI (server.py)
  │  asyncio.create_task(run_deep_agent)
  ▼
run_deep_agent (main_agent.py)
  │  ContextVar: session_dir + thread_id
  │  memory_store.search(query 关键词) → 注入 system prompt
  │  main_agent.astream({messages: [...]}, {configurable: {thread_id}})
  ▼
main_agent (create_deep_agent)
  ├── tools: [generate_markdown, convert_md_to_pdf, read_file_content]
  ├── subagents:
  │   ├── network_search_agent  → internet_search (SearXNG)
  │   ├── database_query_agent  → list_sql_tables / get_table_data / execute_sql_query
  │   └── paper_knowledge_agent → search_paper_library / retrieve_paper_evidence / build_paper_card
  └── checkpointer: InMemorySaver (session 内多轮记忆)
```

**三个关键设计决策**：
1. **SearXNG 替代 Tavily**：零费用、自托管、聚合 70+ 引擎，适合教学与离线部署场景
2. **LlamaIndex 替代 RAGFlow**：本地索引自包含，移除外部服务依赖，BM25+向量 RRF 融合可控
3. **DeepAgents Orchestrator-Workers**：框架原生支持主智能体派发子任务，无需手写调度循环

---

## 二、简历条目拆解

### 条目 1：多智能体编排

> 基于 DeepAgents 与 LangGraph 构建"一主三从"架构，主 Agent 负责任务规划与综述生成，子 Agent 分别处理论文库检索、网络搜索和元数据查询。

#### 实现细节

```python
# app/agent/main_agent.py:44-50
main_agent = create_deep_agent(
    model=model,
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)
```

- **`create_deep_agent` 是 DeepAgents 框架的函数**，内部将 model、tools、subagents 组装成一个 LangGraph `CompiledGraph`。tools 挂载到主智能体，subagents 注册为可调用的"工具"（底层表现为 name="task" 的 tool_call）
- **子智能体是字典定义**，不是独立的 LangGraph 节点。以 network_search_agent 为例：
  ```python
  # app/agent/subagents/network_search_agent.py
  network_search_agent = {
      "name": "公开学术资料搜索助手",
      "description": "负责查询互联网公开学术资料...",
      "system_prompt": "...",
      "tools": [internet_search],
  }
  ```
- **调度机制**：主智能体 LLM 输出 tool_call，其中 `name="task"` 的调用被 DeepAgents 拦截并路由到对应 subagent。subagent 完成后，结果以 ToolMessage 形式返回给主智能体继续推理
- **`checkpointer=InMemorySaver()`**：基于 LangGraph，同一 `thread_id` 的多轮对话复用上下文。输入 `{"configurable": {"thread_id": session_id}}`，LangGraph 自动管理历史 messages

#### 面试问答要点

| 问题 | 回答 |
|------|------|
| 为什么不直接手写 LangGraph 而要套 DeepAgents？ | DeepAgents 封装了 Orchestrator-Workers 模式：自动处理 subagent 的 tool_call 拦截、结果回传、message 组装。手写需要自己实现 subgraph 注册、中断路由和状态合并，DeepAgents 把这几步压缩成一行 `create_deep_agent(subagents=[...])` |
| 子智能体之间能直接通信吗？ | 不能，必须通过主智能体中转。这是有意设计——主智能体作为单一入口做信息聚合和交叉核验，避免子智能体间混乱调用 |
| 如果子智能体长时间没返回怎么办？ | 子智能体 prompt 限制了最大搜索次数（网络搜索 ≤5 次），没有超时机制。生产环境应加 `asyncio.wait_for` 兜底 |

---

### 条目 2：混合检索融合

> 基于 LlamaIndex 构建论文 RAG 链路，结合向量召回、BM25 与重排序，返回带来源片段、页码和相关性分数的证据结果。

#### 实现细节

**完整检索流水线** (`app/tools/llamaindex_tools.py:270-370`)：

```
query
  → LlamaIndex 向量检索 (candidate_k = top_k * candidate_multiplier)
    → BM25Okapi 在同一候选集上计算 BM25 分数
      → RRF 融合 (score = 1/(k+vector_rank) + 1/(k+bm25_rank))
        → [可选] MiniLM 语义重排序 (cosine similarity)
          → 返回 top_k 个片段
```

**向量检索调用**：
```python
# llamaindex_tools.py:294
retriever = index.as_retriever(similarity_top_k=candidate_k)  # candidate_k = max(1, min(top_k * 2, 20))
vector_nodes = retriever.retrieve(query)
```

- `index` 是 `VectorStoreIndex`，使用 LlamaIndex 内置的 `SimpleVectorStore`（默认 mock embedding，可切换 OpenAI / HuggingFace）
- 检索参数由 `retrieval_config.py` 集中控制：
  ```python
  # app/config/retrieval_config.py
  RETRIEVAL_CONFIG = {
      "rrf_k": 30,                # RRF 融合常数
      "enable_reranker": False,    # MiniLM 重排序开关（关闭省 ~13s 加载时间）
      "candidate_multiplier": 2,   # 候选集倍数
      "final_top_k": 5,           # 最终返回条数
      "bm25_tokenizer": None,     # None = split, "jieba" = 中文分词
  }
  ```

**BM25 计算**：
```python
# llamaindex_tools.py:308-319
from rank_bm25 import BM25Okapi
tokenized_corpus = [tokenizer(text) for text in candidate_texts]
bm25 = BM25Okapi(tokenized_corpus)
bm25_scores = bm25.get_scores(tokenized_query)
```

- 英文用 `split()`，中文用 `jieba.cut()`
- BM25 完全不可用时（`max(bm25_scores) < 0.1`）降级到纯向量检索

**RRF 融合**：
```python
# llamaindex_tools.py:330-342
vector_rank = rank_in_vector  # 在候选集中的排序位置
bm25_rank = rank_in_bm25     # 在 BM25 排序中的位置
rrf_score = 1.0 / (rrf_k + vector_rank) + 1.0 / (rrf_k + bm25_rank)
```

**MiniLM 重排序** (`app/tools/rerank_tools.py:69-73`)：
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")  # ~80MB
query_emb = model.encode(query, normalize_embeddings=True)
doc_embs = model.encode(texts, normalize_embeddings=True)
scores = np.dot(doc_embs, query_emb).tolist()  # cosine similarity
```

**父子索引设计**：
- 子块（chunk）命中后，通过 `parent_id` 字段回溯父块原文，用 `LlamaIndex` 的 `NodeRelationship.PARENT` 关系恢复完整上下文

#### 面试问答要点

| 问题 | 回答 |
|------|------|
| 为什么用 RRF 而不是 Convex Combination？ | RRF 不依赖分数归一化，对向量分数和 BM25 分数的尺度差异不敏感。先排序再算分数，比加权平均更鲁棒 |
| MiniLM 重排序为什么默认关闭？ | `all-MiniLM-L6-v2` 首次加载耗时 ~13 秒，在论文库只有 3 篇的小语料上 MRR 提升有限（0.81→0.89），对于实时 Demo 而言加载延迟不可接受 |
| 向量检索用的什么 Embedding？ | `.env` 中 `LLAMAINDEX_EMBED_MODEL` 配置。默认 `mock`（随机向量，仅调试），可切换 `openai`（text-embedding-3-small）或 `local`（all-MiniLM-L6-v2） |

---

### 条目 3：公开搜索与记忆

> 基于 Docker 部署 SearXNG 聚合公开搜索结果，补充 arXiv、GitHub 和论文主页信息；设计长期记忆模块复用历史调研结果。

#### 实现细节

**SearXNG API 调用** (`app/tools/search_tool.py:65-100`)：

```python
# 核心 API 调用
url = f"{SEARXNG_BASE_URL}/search"
params = {"q": query, "format": "json", "categories": category, "pageno": 1}
headers = {"User-Agent": "DeepSearch-Agent/1.0"}
resp = requests.get(url, params=params, headers=headers, timeout=5)
results = resp.json().get("results", [])[:max_results]
```

- **自托管优势**：不限速率、不限额度、聚合 Google/Bing/StackOverflow/GitHub 等 70+ 引擎
- **Category 映射**：`"general"` → SearXNG `"general"`，`"news"` → `"news"`, `"finance"` → `"news"`（回退）
- **结果解析**：保留 `title`、`url`、`content`、`engine`（来源引擎名）、`snippet`（截断 500 字）

**长期记忆系统** (`app/memory/memory_store.py:63-127`)：

```python
# save: 关键词重叠 ≥ 0.5 则覆盖更新，否则追加
if _key_overlap(new_key, existing_key) >= 0.5:
    mem["content"] = content
    mem["updated_at"] = now

# search: 关键词子串匹配（case-insensitive），时间降序
matches = [m for m in self._memories if kw.lower() in m["key"].lower()
           or kw.lower() in m["content"].lower()]

# _key_overlap 算法：词级重叠率
def _key_overlap(self, key1, key2):
    words1 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key1.lower()))
    words2 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key2.lower()))
    return len(words1 & words2) / max(len(words1), len(words2))
```

- **触发时机**：任务开始时，用 query 关键词匹配历史记忆 → 注入 system prompt；任务结束时，存储结果前 500 字
- **不引入向量检索**：关键词子串匹配在 ≤50 条记忆规模下足够高效
- **存储文件**：`output/sessions/memory_store.json`，最多保留 50 条

#### 面试问答要点

| 问题 | 回答 |
|------|------|
| 为什么不用 Tavily？ | 教学与离线部署场景，SearXNG 零费用、可自定义引擎组合（arXiv 搜索结果优于通用搜索引擎） |
| 记忆系统为什么用关键词匹配而不是向量检索？ | 记忆数量 ≤50 条，关键词子串匹配（O(n)）足够；不引入向量检索避免了 embedding 模型依赖和索引维护成本，F1 在阈值 0.5 时达到 0.83 |
| 如果 query 只有"它"怎么匹配历史？ | 单字词被过滤（`len(kw) < 2` 跳过），无匹配则不注入记忆 |

---

### 条目 4：异步与工程化

> 基于 FastAPI + WebSocket 实现异步任务和实时进度推送，通过 thread_id、ContextVar 和会话目录隔离并发任务，并构建评测集支持迭代。

#### 实现细节

**任务提交** (`app/api/server.py:92-116`)：

```python
@app.post("/api/task")
async def run_task(request: TaskRequest):
    if len(request.query) > 2000:
        raise HTTPException(status_code=400)
    thread_id = request.thread_id or str(uuid.uuid4())
    # 同 thread_id 取消旧任务
    if old_task and not old_task.done():
        old_task.cancel()
    task = asyncio.create_task(run_deep_agent(request.query, thread_id))
    active_tasks[thread_id] = task
    task.add_done_callback(lambda t: _forget_task(thread_id, t))
    return {"status": "started", "thread_id": thread_id}
```

**ContextVar 隔离** (`app/api/context.py`)：

```python
_session_dir_ctx = ContextVar("session_dir", default=None)
_thread_id_ctx = ContextVar("thread_id", default=None)

def set_session_context(path: str) -> Token:
    return _session_dir_ctx.set(path)

def get_session_context() -> Optional[str]:
    return _session_dir_ctx.get()
```

- 深层工具调用 `get_session_context()` 获取当前会话目录，无需层层传参
- `finally` 块中 `reset_session_context()` 保证不会串到下一个请求

**WebSocket 事件推送** (`app/api/monitor.py`)：

```python
# 事件格式
payload = {
    "type": "monitor_event",
    "event": "tool_start" | "assistant_call" | "task_result" | "error" | "task_cancelled" | "session_created",
    "message": "开始执行工具: 网络搜索工具",
    "data": {"tool_name": "...", "args": {...}},
    "timestamp": "2026-06-11T14:27:53.738"
}
```

- 跨线程安全性：如果 monitor._emit 在事件循环线程外调用，使用 `asyncio.run_coroutine_threadsafe` 投递
- 审计日志：同时写入 `output/session_{id}/tool_calls.log`

**安全机制**：

| 机制 | 实现 | 位置 |
|------|------|------|
| SQL 只读白名单 | `execute_sql_query` 检查前缀 SELECT/SHOW/WITH/DESCRIBE/EXPLAIN | `db_tools.py:177-183` |
| Query 长度限制 | `len(request.query) > 2000 → 400` | `server.py:101` |
| 路径穿越防护 | `resolve()` + `is_relative_to(output_dir)` | `server.py:278-282`, `path_utils.py` |

**评测体系** (`app/evaluation/evaluate.py`)：

```python
# 三种策略对比
strategies = {
    "纯向量": run_vector_only,
    "混合(BM25+向量)": run_hybrid,
    "全链路(+rerank)": run_full_pipeline,
}
# 指标：Recall@3, Recall@5, Recall@10, MRR
```

- Ground truth：6 条 query，对应 `docs/papers/_ground_truth.json`
- 运行：`uv run python -m app.evaluation.evaluate`

#### 面试问答要点

| 问题 | 回答 |
|------|------|
| 并发请求会互相干扰吗？ | 不会。每个请求独立 `asyncio.create_task`，ContextVar 在每个协程开始时设置、结束时 reset，会话目录按 `session_{thread_id}` 隔离 |
| 如果同时提交两个相同 thread_id 的任务？ | 后一个会取消前一个（`old_task.cancel()`），保证同一会话只有一个活跃任务 |
| WebSocket 断开后还能收到结果吗？ | 不能，当前是实时推送设计。如果需要对离线场景支持，可以加事件持久化到 Redis/数据库，断线重连后拉取 |
| SQL 安全怎么做的？ | 两层：应用层白名单（只允许 SELECT/SHOW/WITH/DESCRIBE/EXPLAIN）；提示词层约束子智能体"只生成 SELECT 类型查询" |

---

## 三、核心 API 调用表

| 组件 | API / 调用 | 方法 | 关键参数 | 返回值 |
|------|-----------|------|----------|--------|
| SearXNG | `{SEARXNG_BASE_URL}/search` | GET | `q`, `format=json`, `categories`, `pageno=1` | `{"results": [{"title","url","content","engine"}]}` |
| LlamaIndex | `index.as_retriever(similarity_top_k=N).retrieve(query)` | 本地调用 | `similarity_top_k` = candidate_k（默认 10） | `[NodeWithScore]` |
| MiniLM | `model.encode(texts, normalize_embeddings=True)` | 本地调用 | `model = "all-MiniLM-L6-v2"` | `np.ndarray` |
| MySQL | `mysql.connector.connect(config)` | TCP | `host`, `port`, `user`, `password`, `database` | Connection |
| MySQL | `cursor.execute(sql)` | 只读 | 仅 `SELECT/SHOW/WITH/DESCRIBE/EXPLAIN` | cursor |
| OpenAI | `init_chat_model(model, model_provider="openai")` | HTTP | `LLM_QWEN_MAX`（model name）, `OPENAI_BASE_URL`, `OPENAI_API_KEY` | ChatModel |
| DeepAgents | `create_deep_agent(model, tools, subagents, checkpointer)` | 组装 | `system_prompt`, `checkpointer` | CompiledAgent |
| DeepAgents | `agent.astream({messages}, config)` | 流式 | `config={"configurable": {"thread_id": id}}` | AsyncGenerator[dict] |
| FastAPI | `POST /api/task` | HTTP | `{"query": str, "thread_id": str \| null}` | `{"status","thread_id"}` |
| FastAPI | `WS /ws/{thread_id}` | WebSocket | path param | JSON events |
| 文档读取 | `PdfReader().pages[i].extract_text()` | 本地 | pypdf | str |
| 文档读取 | `docx.Document().paragraphs` | 本地 | python-docx | list[Paragraph] |
| 文档读取 | `pd.read_excel()` | 本地 | pandas | DataFrame |
| PDF 生成 | ReportLab `SimpleDocTemplate.build(story)` | 本地 | `pageSize=A4`, `STSong-Light` 字体 | PDF file |

---

## 四、LangGraph 与 DeepAgents 技术原理

### 4.1 LangGraph 核心概念与在本项目的映射

LangGraph 是 LangChain 团队开发的**有状态图框架**，核心抽象是 `StateGraph`——一个节点（Node）和边（Edge）组成的有向图，每个节点接收当前状态、执行操作、返回更新后的状态。

| LangGraph 概念 | 在本项目的体现 |
|----------------|---------------|
| **StateGraph** | DeepAgents 内部创建 `StateGraph`，状态类型为 `AgentState`（包含 `messages: list`） |
| **Node** | 每个 node 是一个函数：`(state) -> {"messages": [new_msg]}`。DeepAgents 自动注册 `model`（LLM 调用）、`tool`（工具执行）两类节点 |
| **Edge** | 控制流：`model` → `tool`（当 LLM 返回 tool_calls 时），`tool` → `model`（工具执行完回到 LLM） |
| **Conditional Edge** | LangGraph 内置判断：如果 LLM 输出含 tool_calls，走 tool 分支；否则走到 END |
| **Checkpoint** | `InMemorySaver` 在每个 step 后保存完整 state，支持 `thread_id` 隔离和回溯 |
| **Interrupt** | DeepAgents 用 `interrupt` 实现 subagent 调用——挂起主图执行，启动子图，子图完成后再恢复 |
| **CompiledGraph** | `create_deep_agent` 返回的就是 `CompiledGraph` 实例，可直接 `invoke` 或 `astream` |

### 4.2 DeepAgents 内部图结构

DeepAgents 的 `create_deep_agent` 在 LangGraph 之上做了三层封装：

```
第一层：模型节点 (model_node)
  - 调用 LLM chat.completions API
  - 输出：AIMessage（可能含 tool_calls）

第二层：工具节点 (tool_node)  
  - 遍历 tool_calls，执行对应的 Python 函数
  - tool_call["name"] == "task" 时特殊处理：Routing to Subagent

第三层：子智能体路由 (subagent routing)
  - "task" tool_call 被拦截 → 根据 subagent_type 找到对应子智能体字典
  - 创建子智能体的 LangGraph subgraph（本质是嵌套的 model_node + tool_node）
  - 通过 interrupt 挂起主图 → 执行子图 → 子图完成 → 恢复主图
  - 子图结果以 ToolMessage 形式注入主图的状态
```

**关键区别：普通工具调用 vs 子智能体调用**

```python
# 普通工具调用流程
LLM → tool_call(name="internet_search", args={"query": "..."})
    → tool_node 执行 internet_search(query)
    → ToolMessage(content="搜索结果...") → 回到 LLM

# 子智能体调用流程  
LLM → tool_call(name="task", args={"subagent_type": "network_search_agent", "description": "..."})
    → 拦截器检测到 name="task"
    → 创建子智能体上下文（自己的 system_prompt + tools）
    → interrupt 主图, 启动子图执行
    → 子图内部: model → tool → model → ... → 完成
    → ToolMessage(content="子智能体完整回答") → 恢复主图
```

### 4.3 LangGraph 运行时状态管理

**Checkpoint 机制** (`checkpointer=InMemorySaver()`)：

```python
# LangGraph 内部行为（伪代码）
checkpointer.put(config, run, state)  # 每个 step 后保存
checkpointer.get(config)              # 恢复时读取

# config 必须包含 thread_id
config = {"configurable": {"thread_id": "session_xxx"}}
```

- 同一 `thread_id` 的第二轮调用自动恢复历史 messages，实现多轮对话
- `InMemorySaver` 存储在内存中，服务重启后丢失。生产可用 `SqliteSaver` 或 `PostgresSaver` 持久化
- 每次 `astream` 迭代产生一个 chunk，chunk 结构为 `{node_name: {"messages": [...]}}`

**astream 的 chunk 结构**：

```python
# 典型输出
{"model": {"messages": [AIMessage(content="我来分析这个任务...")]}}
{"tool": {"messages": [ToolMessage(content="搜索结果...", tool_call_id="...")]}}  
{"model": {"messages": [AIMessage(content="根据搜索结果...", tool_calls=[...])]}}
{"task": {"messages": [ToolMessage(content="子智能体完成", name="task")]}}
{"model": {"messages": [AIMessage(content="最终回答...")]}}
```

### 4.4 子智能体的中断与恢复（Interrupt 机制）

DeepAgents 利用 LangGraph 的 `interrupt` 功能实现子智能体调度：

```
主图执行到 model_node
  → LLM 决定调用 subagent (tool_call name="task")
  → tool_node 检测到 task 调用
  → interrupt() 挂起主图执行
  → 创建子智能体的 subgraph（新的 StateGraph）
  → 子图执行：model → tool → model → ... → 完成
  → 子图结果包装成 ToolMessage
  → 恢复主图，ToolMessage 注入主图 state
  → 主图 model_node 继续推理
```

这种设计的好处：
- **子智能体上下文隔离**：子智能体有自己的 system_prompt 和 tools，不会污染主智能体的 prompt
- **嵌套边界可控**：通过 `SubAgentLimits` 控制嵌套深度（默认 5 层），防止无限递归
- **可观察性**：subagent 的 tool_call 和结果在主图的 chunk 中独立呈现

### 4.5 对比：纯 LangGraph 手写 vs DeepAgents

```python
# ── 纯 LangGraph 手写 Orchestrator-Workers（伪代码，约 60 行）──
builder = StateGraph(AgentState)
builder.add_node("model", call_model)
builder.add_node("tools", tool_executor)
builder.add_conditional_edges("model", should_continue, {"continue": "tools", "end": END})
builder.add_edge("tools", "model")
# + 需要手写 subgraph 注册、interrupt 路由、状态合并...
# + 每个子智能体需要单独定义 StateGraph
# + 多轮对话需要手动管理 checkpoint

# ── DeepAgents（1 行）──
agent = create_deep_agent(model=model, tools=[...], subagents=[...], checkpointer=InMemorySaver())
```

### 4.6 LangGraph 的递归限制与安全

DeepAgents 通过 `SubAgentLimits` 防止无限递归：

```bash
# app/agent/subagents/__init__.py 或全局配置
max_depth = 5  # 子智能体最多嵌套 5 层
```

- 超出深度时，LLM 的 `task` tool_call 被拒绝并返回错误消息
- 本项目一主三从只有 2 层（主 → 子），远未触及限制

### 面试问答要点

| 问题 | 回答 |
|------|------|
| DeepAgents 和直接写 LangGraph 比优势在哪？ | 封装了三个常见模式：① Orchestrator-Workers 的 subagent 注册与路由；② interrupt/subgraph 的样板代码；③ tool_call 的拦截与消息组装。让开发者聚焦 Prompt 和工具定义 |
| 如果我想给子智能体加一个独立的 checkpointer 怎么做？ | DeepAgents 的子智能体是字典定义，不支持独立 checkpoint。需要手动创建 `CompiledSubAgent`（DeepAgents 的类），传入独立的 checkpointer |
| astream 的 chunk 里为什么经常出现空消息？ | LangGraph 的 state reducer 是 append 模式，每个 node 都可能产生空 messages 字段。代码中通过 `if not state or "messages" not in state: continue` 跳过 |
| InMemorySaver 重启丢了怎么办？ | 当前设计如此。生产可以换 `SqliteSaver`（`from langgraph.checkpoint.sqlite import SqliteSaver`），LangGraph 支持完全相同的接口 |
| 子智能体的 tool_call 日志怎么区分是哪个 agent 调用的？ | 通过 `get_thread_context()` 拿到 `thread_id`，再通过 chunk 中 node_name 区分（model 是主智能体，task 是子智能体） |

---

## 五、面试常见追问

### 架构设计类

**Q: 为什么用 DeepAgents 而不是直接 LangGraph？**
A: DeepAgents 封装了 Orchestrator-Workers 模式的核心逻辑——subagent 注册、tool_call 拦截与路由、结果回传。如果用纯 LangGraph，需要手写 `StateGraph` + `interrupt` + subgraph 嵌套 30+ 行样板代码。`create_deep_agent` 一行代替。

**Q: 如果某个子智能体一直不返回怎么办？**
A: 当前没有超时机制。改进方向：在 `run_deep_agent` 中用 `asyncio.wait_for(astream, timeout=300)` 包装。也可以在 LangGraph 层面加 `max_execution_time` 参数。

**Q: 提示词是怎么管理的？为什么用 YAML？**
A: YAML 文件集中管理所有智能体提示词，修改提示词不需要改 Python 代码。`prompts.py` 用 `yaml.safe_load` + 路径搜索加载。子智能体的 name 和 description 也定义在 YAML 中，主智能体通过 description 判断是否分派任务。

**Q: 主智能体怎么决定调用哪个子智能体？**
A: 纯 LLM 决策。`create_deep_agent` 将每个子智能体的 `name` + `description` 注入到主智能体的 system prompt 的工具描述中。LLM 通过语义匹配用户 query 和子智能体 description，输出 `tool_call(name="task", args={"subagent_type": "...", "description": "..."})`，DeepAgents 拦截后路由到对应的子智能体。

**Q: 同一 thread_id 多轮对话的上下文不会太长导致 token 超限吗？**
A: 会。当前没有做 context window 管理。改进方向：在 system prompt 中加摘要指令，或接入 DeepAgents 的中间件（Middleware）在每次 model_node 前压缩历史 messages。

**Q: LangGraph 的状态更新机制是 replace 还是 append？**
A: 取决于 state schema 中每个 key 的 reducer。对于 `messages`，LangGraph 内置了 `add_messages` reducer（append 模式），新消息追加到列表末尾。DeepAgents 沿用这个模式。

**Q: interrupt 和 checkpointer 的关系是什么？**
A: `interrupt` 是图的执行控制原语（挂起/恢复），`checkpointer` 是状态持久化机制。两者配合使用：interrupt 时 checkpoint 保存当前状态便于恢复；恢复时从 checkpoint 读取状态继续执行。子智能体调度 = interrupt 挂起主图 + 启动子图 + checkpoint 保存 + 子图完成后恢复。

**Q: LangGraph 的 State 里如果放了太多东西会不会影响性能？**
A: 会。LangGraph 的 checkpoint 每次都会序列化整个 state。本项目 state 只有 `messages` 列表，大消息（如 PDF 全文）通过 `read_file_content` 工具读取，不存入 state。这是有意设计。

### 检索类

**Q: 为什么向量检索的 embedding 默认是 mock？**
A: `.env` 默认 `LLAMAINDEX_EMBED_MODEL=mock`，这是为了方便快速测试。生产应改为 `openai` 或 `local`。

**Q: BM25 的词法分析怎么处理的？英文和中文一样吗？**
A: 不一样。返回 config `bm25_tokenizer: None` 时用 `text.split()`（空格分词），设为 `"jieba"` 时用 `jieba.cut`。英文论文场景下 `split` 优于 `jieba`。

**Q: RRF 的 k 值为什么选 30？有实验依据吗？**
A: 实验发现 k=5~60 对结果影响不显著，取中间值 30。见检索参数配置中的注释。

**Q: 向量检索和 BM25 结果差异很大的时候 RRF 还能正常工作吗？**
A: 能。RRF 只用排序位置（rank），不用分数绝对值。即使向量和 BM25 给出的分数尺度完全不同，RRF 仍然稳定。这是 RRF 相对于加权平均的核心优势。

**Q: LlamaIndex 的索引是怎么持久化的？增量更新怎么做的？**
A: `index.storage_context.persist(persist_dir=INDEX_DIR)` 持久化到 `app/storage/paper_index/`。通过 `_paper_manifest.json`（文件路径+大小+修改时间的哈希摘要）检测是否有新文件或文件变更，有变更则全量重建索引。论文库规模小（≤10 个文件），重建耗时可接受。

**Q: 为什么不用 Elasticsearch 做 BM25？直接用 rank_bm25 和 Elasticsearch 比有什么优缺点？**
A: `rank_bm25` 是内存计算，直接在向量检索的候选集上算，避免了 ES 的 HTTP 开销和索引同步成本。缺点是不能处理全库检索——BM25 只在 `candidate_multiplier * top_k` 个候选上计算，如果向量检索漏掉了相关文档，BM25 也无法弥补。ES 的方案可以做到向量 + BM25 双路独立检索再融合，召回率更高但架构更重。

### RAG 与知识库类

**Q: 父子索引的 chunk 策略怎么设计的？为什么 chunk_size=512, overlap=64？**
A: `SentenceSplitter(chunk_size=512, chunk_overlap=64)`。512 是平衡语义完整性和检索精度的经验值：太短（128）丢失上下文，太长（1024）单个 chunk 包含多个主题降低检索精度。64 的 overlap 保证跨段句子的连续性。

**Q: 返回给 LLM 的上下文片段包含什么字段？**
A: 固定格式的证据块：`来源文件`、`页码范围`、`相关性分数`、`内容节选（前 900 字）`。另外注入 `source_type: "knowledge_base"` 字段让主智能体能区分信息来源的可靠性。

**Q: 多源信息交叉，来源冲突怎么处理？**
A: 交给主智能体的 LLM 自行判断。prompt 中明确要求"对同一结论尽量使用多来源信息交叉核验"，如果矛盾则标注"待核验"。没有做自动冲突检测。

**Q: 评测集多大？指标为什么选 MRR 和 Recall@K？**
A: 6 条 query，每条标注了对应的 ground truth 文档 ID。Recall@K 衡量是否召回到正确文档，MRR 衡量最相关文档的排序位置——这对 RAG 任务很关键，因为 LLM 对排序靠前的片段利用率更高。

### 工程类

**Q: ContextVar 为什么比传参好？**
A: 工具和子智能体在 DeepAgents 内部三层调用栈深处，显式传 `session_dir` 需要穿透每一层函数签名。ContextVar 让 `get_session_context()` 在任何深度直接获取。

**Q: WebSocket 事件的线程安全性怎么保证？**
A: `monitor._emit()` 检测当前是否在主事件循环线程：同一线程直接 `create_task`，不同线程用 `asyncio.run_coroutine_threadsafe` 投递。

**Q: 文件上传的流式处理怎么实现的？**
A: `shutil.copyfileobj(file.file, buffer)` 按块复制，不将整个文件读入内存。

**Q: 怎么防止模型穿越目录？**
A: `path_utils.resolve_path()` 将模型输出的虚拟路径（如 `/workspace/report.md`）映射到 `session_dir`，`resolve()` 消除 `../`，再 `is_relative_to(output_dir)` 最终检查。

**Q: 如果用户上传了恶意文件怎么办？**
A: 当前没有文件安全扫描。上传文件仅通过扩展名过滤（knowledge upload 只接受 .pdf），但不做内容检查。生产应加 ClamAV 或类似扫描器。

**Q: 服务重启后正在执行的任务怎么办？**
A: 丢失。`active_tasks` 存储在内存字典中，重启后清空。`InMemorySaver` 同样丢失。生产应用应配合 `SqliteSaver` + 任务队列持久化。

**Q: 并发 100 个请求会怎样？**
A: 每个请求是一个 `asyncio.Task`，受 CPU 和 LLM API 速率限制。如果没有速率控制，100 个并发请求可能打满 LLM API 配额。当前 FastAPI 服务本身没有限流，生产应加 `slowapi` 或类似中间件。

**Q: 前端 WebSocket 断线重连怎么做的？**
A: 前端 `useDeepAgentSession.ts` hook 通过浏览器的 WebSocket API 的 `onclose` / `onerror` 事件触发重连，每次重连后重新生成或使用 localStorage 中缓存的 thread_id 发起连接。但断连期间产生的事件不会补推。

**Q: 为什么用 ReportLab 生成 PDF 而不是 WeasyPrint 或 Puppeteer？**
A: ReportLab 不需要安装系统级依赖（WeasyPrint 需要 libpango、Puppeteer 需要 Chromium），在 Docker Alpine 镜像中部署最轻量。代价是只能手写排版逻辑，不支持 CSS。

**Q: long-term memory 的 search 只用了关键词子串匹配，如果用户换一种说法问同一个问题怎么办？**
A: 确实会有遗漏。当前设计的前提是记忆条目数 ≤50，在这个规模下关键词匹配足够处理大多数重复查询。如果扩展到上百条，应引入语义检索。
