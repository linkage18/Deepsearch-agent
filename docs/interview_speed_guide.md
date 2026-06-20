# 项目面试速懂手册

## 1. 项目一句话概括

> 面向科研文献调研场景，基于 DeepAgents + LangGraph 构建多智能体论文研读系统，实现主题输入、多源检索、结构化证据链与 Markdown/PDF 综述导出。

---

## 2. 项目整体架构

### 2.1 架构总览

项目分为四层，从用户交互到持久化：

| 层 | 技术 | 职责 |
|----|------|------|
| 用户交互层 | React + Vite + Ant Design | 提交任务、上传文件、WebSocket 展示执行过程、下载产物 |
| API 服务层 | FastAPI + Uvicorn + WebSocket | 接收 HTTP 请求、启动后台 asyncio 协程、WebSocket 实时推送 |
| Agent 编排层 | DeepAgents + LangGraph + LangChain | 一主三从状态图、interrupt 子智能体调度、InMemorySaver checkpoint |
| 数据与检索层 | LlamaIndex / SearXNG / MySQL / SQLite | 论文向量检索、网络搜索、结构化查询、全量持久化 |

所有运行时数据统一写入 `data/` 目录（由 `app/config/paths.py` 的 `DATA_ROOT` 控制），Docker 部署时只挂载这一个目录。

### 2.2 核心流程图

```mermaid
flowchart TD
    A[用户提交 research query] --> B[POST /api/task]
    B --> C[asyncio.create_task 后台协程]
    C --> D[run_deep_agent]
    D --> E[创建 data/reports/session_{id} 目录]
    E --> F[ContextVar 写入 session_dir + thread_id]
    F --> G[长期记忆检索注入]
    G --> H[main_agent.astream 启动 LangGraph 图]
    H --> I{LLM Node 决策}
    I -->|需要信息| J[Tool Node]
    J --> K{tool_call.name 判断}
    K -->|"task"| L[Interrupt 主图]
    L --> M[子智能体 Subgraph]
    M --> N[SearXNG / MySQL / LlamaIndex]
    N --> O[ToolMessage 回传]
    O --> I
    K -->|"generate_markdown"| P[写入 .md 文件]
    K -->|"convert_md_to_pdf"| Q[ReportLab 渲染 PDF]
    K -->|"read_file_content"| R[pypdf / python-docx / pandas]
    I -->|无 tool_calls| S[最终回答]
    S --> T[WebSocket 推送 task_result]
    S --> U[持久化到 SQLite: 会话/事件/记忆]
```

---

## 3. 核心模块拆解

### 3.1 DeepAgents + LangGraph 流程编排

#### 3.1.1 抽象原理

本项目的核心不是单轮问答，而是多步推理 + 多源检索 + 文件生成的复杂流程。如果写普通 Python 函数，需要手动维护调用链、状态传递、分支跳转和错误恢复。LangGraph 提供有向图执行引擎，每个步骤是一个 Node，状态通过中心化 State 传递。DeepAgents 在此基础上封装了 Orchestrator-Workers 模式，让子智能体以字典定义注册，框架自动处理路由和中断恢复。

不用它：需要手写 while 循环解析 LLM 的 tool_call、管理 subgraph 嵌套、实现 interrupt 挂起/恢复，约 60-80 行样板代码。

#### 3.1.2 代码实现

**相关文件：**
- `app/agent/main_agent.py:44-50` — 主智能体组装
- `app/agent/main_agent.py:56-241` — run_deep_agent 执行入口
- `app/agent/subagents/network_search_agent.py` — 网络搜索助手定义
- `app/agent/subagents/database_query_agent.py` — 数据库助手定义
- `app/agent/subagents/paper_knowledge_agent.py` — 论文库助手定义
- `app/agent/llm.py:17-19` — 模型初始化
- `app/agent/prompts.py` — YAML 提示词加载

**核心组装**（`main_agent.py:44-50`）：
```python
main_agent = create_deep_agent(
    model=model,                              # langchain OpenAI 兼容模型
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),             # LangGraph checkpoint
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)
```

**子智能体定义**（以 `network_search_agent.py:16-21` 为例）：
```python
network_search_agent = {
    "name": sub_agents_content["tavily"]["name"],
    "description": sub_agents_content["tavily"]["description"],
    "system_prompt": sub_agents_content["tavily"]["system_prompt"],
    "tools": [internet_search],
}
```

**执行入口**（`main_agent.py:154-156`）：
```python
async for chunk in main_agent.astream(
    {"messages": [{"role": "user", "content": task_query + path_instruction}]},
    config=config,
):
```

- **输入**：query + path_instruction（工作目录指令）+ memory_hint（历史记忆）
- **输出**：chunk 流，格式 `{"node_name": {"messages": [...]}}`
- **异常**：CancelledError → report_task_cancelled 后 re-raise；普通 Exception → monitor._emit("error")
- **上下文传递**：`app/api/context.py` 的 ContextVar，深层工具通过 `get_session_context()` 获取

**子智能体调度检测**（`main_agent.py:166-178`）：
```python
if node_name == "model" and last_msg.tool_calls:
    for tool_call in last_msg.tool_calls:
        if tool_call["name"] == "task":
            # 子智能体调用 → report_assistant
            monitor.report_assistant(
                tool_call["args"]["subagent_type"], {...}
            )
        # 其他 tool_call → report_tool
```

#### 3.1.3 面试官会怎么理解

体现能力：Agent 流程编排能力、框架选型判断力、异步编程能力、理解"为什么选这个框架而不选另一个"的技术判断力。

#### 3.1.4 高频追问与回答

**问题 1：为什么选 DeepAgents 而不是直接手写 LangGraph？**

回答：DeepAgents 封装了 Orchestrator-Workers 模式的样板代码。如果手写 LangGraph，需要自己定义 StateGraph、注册 model_node 和 tool_node、写条件边判断 LLM 是否该调工具、手动管理 interrupt 和 subgraph，每个子智能体还得单独定义 subgraph。DeepAgents 把这几步压缩成一行 `create_deep_agent(subagents=[...])`。我这里一主三从，正好匹配 Orchestrator-Workers 模式。如果未来需要更复杂的图结构（如并行节点、条件分支），我会直接上纯 LangGraph。

**问题 2：主智能体怎么决定调用哪个子智能体？**

回答：完全由 LLM 自行决策。create_deep_agent 会把每个子智能体的 name 和 description 注入主智能体的 system prompt 的工具定义中。LLM 根据用户 query 的语义匹配子智能体的 description，输出 tool_call(name="task", args={subagent_type: "网络搜索助手"})。DeepAgents 拦截 name="task" 的调用，按 subagent_type 路由。这和普通 tool_call 的区别是它触发 interrupt 挂起主图，而不是在当前节点内同步执行。

**问题 3：astream 的 chunk 结构是什么？你怎么区分主智能体和子智能体的输出？**

回答：chunk 格式是 `{"节点名": {"messages": [消息]}}`。当 `node_name == "model"` 时是主 LLM 输出。我检查 `last_msg.tool_calls`：如果 `tool_call.name == "task"` 说明在调子智能体，调用 `report_assistant()` 通知前端。子智能体内部的 tool_call 不会出现在主图 chunk 中，因为子图执行期间主图被 interrupt 挂起了。子图完成后结果以 ToolMessage 回注主图 state。

#### 3.1.5 不能乱说的点

- ❌ 不要说"我手写了 LangGraph 完整的图控制逻辑" — 实际用的是 DeepAgents 封装
- ❌ 不要说"子智能体之间可以直接通信" — 只能通过主智能体中转
- ❌ 不要说"支持分布式高可用" — InMemorySaver 是单机内存存储
- ❌ 不要说"做了模型微调" — 没有微调脚本

---

### 3.2 RAG 检索链路（LlamaIndex + BM25 + RRF + MiniLM）

#### 3.2.1 抽象原理

RAG 通过在生成前检索相关知识，解决 LLM 知识过时和幻觉问题。本项目在检索上做了三层增强：向量召回负责语义相似度匹配，BM25 负责关键词精确命中，MiniLM 做最终排序精排。第三层的重排序默认关闭（加载 ~13 秒），但在评测场景下 MRR 从 0.61 提升到 0.89。

#### 3.2.2 代码实现

**相关文件：**
- `app/tools/llamaindex_tools.py:270-370` — 检索管线
- `app/tools/rerank_tools.py:43-83` — MiniLM 重排序
- `app/config/retrieval_config.py` — 参数配置
- `app/evaluation/evaluate.py` — 评测脚本

**四步检索流水线**（`llamaindex_tools.py`）：

```python
# 1. 向量检索取候选
candidate_k = max(1, min(top_k * 2, 20))   # config.candidate_multiplier = 2
retriever = index.as_retriever(similarity_top_k=candidate_k)
vector_nodes = retriever.retrieve(query)

# 2. BM25 在同一候选集上计算
from rank_bm25 import BM25Okapi
tokenized_corpus = [tokenizer(t) for t in texts]  # split 或 jieba
bm25 = BM25Okapi(tokenized_corpus)
bm25_scores = bm25.get_scores(tokenized_query)

# 3. RRF 融合
rrf_k = 30
for rank, node in enumerate(vector_nodes):
    rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)

# 降级兜底: BM25 完全失效时纯向量
if max(bm25_scores) < 0.1:
    fused_nodes = vector_nodes

# 4. [可选] MiniLM 重排序
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
query_emb = model.encode(query, normalize_embeddings=True)
doc_embs = model.encode(texts, normalize_embeddings=True)
scores = np.dot(doc_embs, query_emb).tolist()
```

**索引配置**（`llamaindex_tools.py` 约 200-213 行）：
```python
PAPER_DIR = "data/papers/"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
SentenceSplitter(chunk_size=512, chunk_overlap=64)
```

**可调参数**（`app/config/retrieval_config.py`）：
```python
RETRIEVAL_CONFIG = {
    "rrf_k": 30,
    "enable_reranker": False,
    "candidate_multiplier": 2,
    "final_top_k": 5,
    "bm25_tokenizer": None,  # None=split, "jieba"=中文
}
```

**评测结果**（来自 `evaluate.py`）：
```
| Strategy | Recall@3 | Recall@5 | Recall@10 | MRR |
| 纯向量   | 0.1500   | 0.1500   | 0.1500    | 0.1500 |
| 混合     | 0.3750   | 0.3750   | 0.3750    | 0.3917 |
| 全链路   | 0.4000   | 0.4500   | 0.4500    | 0.4167 |
```

#### 3.2.3 面试官会怎么理解

体现能力：RAG 工程化能力、检索优化意识、评测意识、理解每一步选择的 trade-off。

#### 3.2.4 高频追问与回答

**问题 1：为什么用 RRF 而不是加权平均或 Convex Combination？**

回答：RRF 只用排序位置，不依赖分数归一化。向量检索返回的相似度分数和 BM25 分数尺度可能差几个数量级——向量分数是 0.8，BM25 是 50。加权平均需要调权重，而且分数尺度一旦变化权重就得重调。RRF 对尺度不敏感，`1/(k+rank)` 在任何分数分布下都能稳定工作。实验也验证了 k=5~60 对结果影响不显著，说明 RRF 很鲁棒。

**问题 2：MiniLM 重排序为什么默认关闭？**

回答：all-MiniLM-L6-v2 首次需要下载模型 ~80MB，加载耗时约 13 秒。在论文库只有 3-10 篇的小语料上，加上重排序 MRR 提升 2.5%（0.3917 → 0.4167），但 Demo 时用户要等 13 秒加载模型，体验不可接受。所以设计了 `enable_reranker` 开关，生产环境可以开启，Demo 场景关闭。

**问题 3：Embedding 模型为什么是可切换的？**

回答：三种模式解决不同场景：mock 模式用随机向量，不需要任何外部依赖，适合 CI 测试和调试。local 模式用本地 sentence-transformers 模型，完全离线。openai 模式用 text-embedding-3-small，质量最高但需要 API Key 和网络。通过 `.env` 的 `LLAMAINDEX_EMBED_MODEL` 切换，不改代码。

#### 3.2.5 不能乱说的点

- ❌ 不要说"做了知识图谱检索" — 没有知识图谱
- ❌ 不要说"EBM25 或 learning-to-rank" — 用的是基础 BM25 + RRF
- ❌ 不要夸大数据规模 — 论文库只有 10 个文件
- ❌ 不要说 recall@k 很高 — 20 条 query 上全链路 Recall@3 只有 0.4

---

### 3.3 结构化证据链

#### 3.3.1 抽象原理

传统 RAG 返回一段拼接文本，Agent 引用时无法精确追踪到来源。本项目将检索结果结构化为标准 evidence 对象（含 source/page/score/quote/metadata），持久化到 SQLite。Agent 在生成结论时必须用 `【证据: evidence_id】` 或 `【来源: 标题, p.5】` 格式绑定来源，否则系统可自动校验引用真伪。

没有这个模块：Agent 说"据研究报告显示"你无法验证它说的是哪份报告、哪一页、原文是什么。

#### 3.3.2 代码实现

**相关文件：**
- `app/tools/llamaindex_tools.py:233-246` — evidence 格式化输出
- `app/models/session.py:299-371` — evidence_records 表 CRUD
- `app/api/server.py:217-256` — 检索测试接口 + 证据查询接口

**evidence 结构**（`llamaindex_tools.py`）：
```python
evidence_item = {
    "evidence_id": "kb-1",
    "source_type": "knowledge_base",
    "source": "react-pattern.md",
    "page": "5",
    "score": 0.85,
    "quote": "# ReAct: Synergizing Reasoning...",
    "metadata": {"file_path": "...", "file_name": "react-pattern.md"},
}
```

**持久化**（`session.py:299-334`）：
```python
def save_evidence_records(query, evidence, thread_id=None):
    # 将 evidence 数组写入 evidence_records 表
    # 每条包含: thread_id, query, evidence_id, source_type, source, page, score, quote, metadata_json
```

**检索测试接口**（`server.py:217-246`）：
```python
@app.post("/api/retrieval/test")
async def retrieval_test(request):
    retrieval = search_paper_evidence_structured(query, top_k)
    saved_count = save_evidence_records(query, retrieval["evidence"])
    return {"query": query, "evidence": retrieval["evidence"], "saved_count": saved_count}
```

#### 3.3.3 面试官会怎么理解

体现能力：RAG 结果的结构化思维能力、数据建模能力、前端可观测性设计意识。

#### 3.3.4 高频追问与回答

**问题 1：证据结构化和纯文本拼接相比有什么好处？**

回答：三个好处。第一，前端可以按来源/页码/分数/原文逐条展示证据卡片，面试演示非常直观，面试官一眼就能看到每段结论来自哪篇论文的哪一页。第二，证据持久化到 SQLite 后，后续的引用校验模块可以直接查表匹配，不需要重新检索。第三，metadata 字段可以携带文件路径、页码标签等额外信息，前端和后端都能灵活扩展。

**问题 2：evidence_id 怎么生成的？会不会重复？**

回答：目前是简单的顺序编号加前缀，如 `kb-1`、`kb-2`。在小语料下够用。如果要做生产级，应该用 UUID 或内容哈希来保证全局唯一。这也是我下一步会改进的地方。

#### 3.3.5 不能乱说的点

- ❌ 不要说"evidence_id 是 UUID 或全局唯一标识" — 实际是简单的 `kb-N` 编号
- ❌ 不要说"支持跨批量证据去重" — 没有去重逻辑

---

### 3.4 引用自动校验

#### 3.4.1 抽象原理

Agent 生成的报告中可能包含编造的引用。传统做法靠 prompt 约束，但无法验证。本模块作为后置步骤，提取报告中的 `【证据: xxx】` 标记，到 evidence_records 表匹配真实证据，用 MiniLM 计算 claim 与原文的语义相似度，输出量化指标（覆盖率、unfounded 率）。

没有这个模块：面试官问"你怎么保证引用是真实的？"只能回答"我在 prompt 里写了要引用来源"——没有任何说服力。

#### 3.4.2 代码实现

**相关文件：**
- `app/tools/citation_checker.py` — 校验模块（232 行）
- `app/models/session.py` — citation_checks 表 + CRUD

**校验流程**（`citation_checker.py:118-232`）：

```python
# 1. 提取声明标记
claims = extract_claims(report_text)
# 正则: [【]证据:\s*([^】]+?)[】] 和 [【]来源:\s*([^】]+?)(?:,\s*p.?s*(\d+))?[】]

# 2. 查 evidence_records 表建立索引
evidence_records = list_evidence_records(limit=500)
evidence_by_id[eid] = rec

# 3. 对每个 claim 匹配证据
for claim in claims:
    # Priority 1: evidence_id 精确匹配
    for eid in claim["evidence_ids"]:
        matched_quote = evidence_by_id[eid].get("quote")
        similarity = _cosine_similarity(claim_sentence, matched_quote)
        # ≥0.5 verified / ≥0.25 low_confidence / <0.25 unfounded

    # Priority 2: source title + page 匹配
    if status == "unfounded":
        # 按来源标题和页码匹配 evidence_by_source

# 4. 写入 citation_checks 表
save_citation_check(thread_id, report_id, claim_snippet, status, similarity_score)
```

**证据编号提取正则**（`citation_checker.py:24-25`）：
```python
_EVIDENCE_PATTERN = re.compile(r'[\[【]证据:\s*([^\]】]+?)[\]】]')
_SOURCE_PATTERN = re.compile(r'[\[【]来源:\s*([^\]】]+?)(?:,\s*p[.．]?\s*(\d+))?[\]】]')
```

**API 接口**（`server.py`）：
- `POST /api/report/{thread_id}/verify` — 触发校验
- `GET /api/report/{thread_id}/verification` — 查询校验统计

#### 3.4.3 面试官会怎么理解

体现能力：引用可信度的工程方案设计能力（不靠 prompt 承诺，靠系统验证）、文本解析能力、语义匹配能力。

#### 3.4.4 高频追问与回答

**问题 1：如果模型不可用或加载失败怎么办？**

回答：做了兜底。`_cosine_similarity` 函数内部 try-except 捕获所有异常，如果模型加载失败或计算异常直接返回 None。调用方检测到 None 时按 verified 处理——因为 evidence_id 精确匹配本身已经是强证据了，语义相似度是额外的质量信号，不是必要条件。系统不会因为模型挂了就罢工。

**问题 2：阈值 0.5 和 0.25 怎么确定的？**

回答：实验调出来的。用 MiniLM 对 claim 和 evience quote 做相似度，短 claim（20-50 字） vs 长 quote（200-500 字）的余弦相似度天然偏低。0.7 的阈值会导致几乎全部判为 low_confidence。实测 0.5 能较好地区分"语义相关"和"语义无关"，0.25 是区分"弱相关"和"完全不相关"的边界。如果换更大的模型（如 all-mpnet-base-v2），阈值可以相应调高。

#### 3.4.5 不能乱说的点

- ❌ 不要说"引用校验精确率 95% 以上" — 没有做精确率评测
- ❌ 不要说"支持 LLM 交叉验证" — 没有用 LLM 做验证
- ❌ 不要说"能自动修正错误引用" — 只能标记，不修正

---

### 3.5 长期记忆

#### 3.5.1 抽象原理

Agent 每轮任务结束后，将关键结论保存到长期记忆。下次任务启动时，用 query 关键词匹配历史记忆，匹配到的注入 system prompt。这样用户可以在新任务中复用之前的调研结论。

#### 3.5.2 代码实现

**相关文件：**
- `app/memory/memory_store.py`

**保存时机**（`main_agent.py:198-212`）：
```python
if final_result:
    content = final_result[:500]  # 取前 500 字
    h1_match = re.search(r'^#\s+(.+)$', final_result, re.MULTILINE)  # 取第一个标题
    memory_key = h1_match.group(1) if h1_match else task_query[:80]
    memory_store.save(memory_key, content, session_id)
```

**检索时机**（`main_agent.py:126-148`）：
```python
keywords = re.split(r'[,，?\s]+', task_query)
for kw in keywords:
    if len(kw) < 2: continue
    matches = memory_store.search(kw)  # 关键词子串匹配
    memory_hint += f"\n- [{key}]: {content_preview}"
```

**存储格式**（`memory_store.py`）：
```python
{
    "key": "MIM-Reasoner 核心方法",
    "content": "前 500 字...",
    "session_id": "xxx",
    "created_at": "2026-06-11T...",
    "updated_at": "2026-06-11T..."
}
```

#### 3.5.3 不能乱说的点

- ❌ 不要说"语义检索长期记忆" — 用的只是关键词子串匹配
- ❌ 不要说"支持上万条记忆" — JSON 文件最多 50 条

---

### 3.6 FastAPI 异步服务与 WebSocket

#### 3.6.1 抽象原理

深度研究任务可能耗时数分钟，不能阻塞 HTTP 请求。FastAPI 使用 `asyncio.create_task` 将 Agent 执行丢到后台，立即返回 thread_id。前端同时打开 WebSocket 连接接收实时事件。

#### 3.6.2 代码实现

**相关文件：**
- `app/api/server.py` — 全部接口
- `app/api/monitor.py` — WebSocket 事件推送

**任务启动**（`server.py:153-177`）：
```python
@app.post("/api/task")
async def run_task(request):
    if len(request.query) > 2000:
        raise HTTPException(status_code=400)
    thread_id = request.thread_id or str(uuid.uuid4())
    old_task = active_tasks.get(thread_id)
    if old_task and not old_task.done():
        old_task.cancel()
    task = asyncio.create_task(_run_agent_with_limits(query, thread_id))
    # _run_agent_with_limits 内部使用 Semaphore 限流 + wait_for 超时
```

**WebSocket 事件**（`monitor.py:40-59`）：
```python
payload = {
    "type": "monitor_event",
    "event": "tool_start" | "assistant_call" | "task_result" | "task_cancelled",
    "message": "...",
    "data": {"tool_name": "...", "args": {...}},
    "timestamp": "..."
}
```

**跨线程安全**（`monitor.py:110-119`）：
```python
if current_loop and current_loop == manager_loop:
    current_loop.create_task(coroutine)  # 同一线程
else:
    asyncio.run_coroutine_threadsafe(coroutine, manager_loop)  # 跨线程投递
```

#### 3.6.3 不能乱说的点

- ❌ 不要说"支持水平扩展" — active_tasks 在单机内存中
- ❌ 不要说"WebSocket 断线后事件不丢" — 断线期间的事件不会补推（但可以主动拉历史）

---

### 3.7 安全控制

#### 3.7.1 代码实现

**SQL 防护**（`app/tools/db_tools.py`）：
```python
# 1. 前缀白名单
if not any(sql_upper.startswith(kw) for kw in ("SELECT","SHOW","WITH","DESCRIBE","EXPLAIN")):
    return "拒绝执行：只允许只读查询"
# 2. 多语句拦截（拒绝分号）
# 3. 表名白名单 + 反引号转义
# 4. 查询结果限制行数
```

**路径防护**（`app/utils/path_utils.py` + `server.py:278-282`）：
```python
abs_path = Path(path).resolve()
output_abs = output_dir.resolve()
if not abs_path.is_relative_to(output_abs):
    return {"error": "拒绝访问"}
```

**其他**：
- Query 长度 ≤ 2000
- 上传 ≤ 5 文件 / ≤ 20MB / 后缀白名单
- Agent 限流 max 4 并发 / 超时 300s
- 健康检查 `/health/live` + `/health/ready`

---

### 3.8 评测体系

#### 3.8.1 代码实现

**相关文件：**
- `app/evaluation/evaluate.py` — 308 行

**三种策略对比**：
```python
strategies = {
    "纯向量": run_vector_only,
    "混合(BM25+向量)": run_hybrid,
    "全链路(+rerank)": run_full_pipeline,
}
```

**指标**：Recall@3 / Recall@5 / Recall@10 / MRR

**CLI**：
```bash
uv run python -m app.evaluation.evaluate --format md  # Markdown 表格输出
```

---

## 4. 关键技术原理速懂

### 4.1 LangGraph StateGraph

**一句话解释**：有向图执行引擎，每个节点是函数，状态通过中心化 State 对象在节点间传递。

**为什么项目需要它**：Agent 执行包含多步推理和工具调用，需要循环（LLM → 工具 → LLM → ...），普通函数调用无法自然表达这种循环。

**代码中怎么体现**：`main_agent.py:44` 的 `create_deep_agent()` 内部创建 LangGraph StateGraph。

**面试口径**：LangGraph 的核心是 StateGraph，你把每个步骤定义为一个 node，node 之间通过 state 传递数据。LangGraph 内置了 add_messages reducer，新的消息自动追加到历史。最关键的条件边——如果 LLM 输出 tool_calls 就走 tools 节点，否则结束——这是 Agent 循环的核心。本项目一主三从的架构就是在 StateGraph 上挂了 4 个节点：model_node 负责推理，tool_node 执行工具，subagent 节点内部又是独立的子图。

### 4.2 DeepAgents create_deep_agent

**一句话解释**：DeepAgents 是封装了 Orchestrator-Workers 模式的框架，一行代码完成主智能体 + 子智能体的注册和路由。

**为什么项目需要它**：省去 60 行手写 LangGraph 样板代码。

**代码中怎么体现**：`main_agent.py:44-50`。

**面试口径**：create_deep_agent 内部做了几件事：创建 StateGraph、注册 model_node、注册 tool_node、注册条件边。它把子智能体当成特殊的工具——当 LLM 输出 name="task" 的 tool_call 时，DeepAgents 会拦截它，查找已注册的字典式子智能体，通过 interrupt 挂起主图，执行子图，结果以 ToolMessage 回传。

### 4.3 RRF（Reciprocal Rank Fusion）

**一句话解释**：多路检索结果融合算法，用排序位置倒数的加权和作为融合分数。

**为什么项目需要它**：向量检索和 BM25 分数尺度不同，不能直接加权平均。RRF 只用排序位置，不依赖分数。

**代码中怎么体现**：`llamaindex_tools.py:330-342`，`rrf_score = 1/(k+vec_rank) + 1/(k+bm25_rank)`。

**面试口径**：RRF 的优点是鲁棒。向量检索返回的分数可能是 0.8，BM25 可能是 50，加权平均需要调权重。RRF 不管分数本身，只看排序位置。即使某一路的分数分布变了，RRF 依然稳定。本项目用 k=30。

### 4.4 BM25

**一句话解释**：经典的概率检索模型，通过词频和逆文档频率计算文档和查询的相关性。

**为什么项目需要它**：向量检索对专有名词、缩写（如"ReAct"、"MIM"）的匹配不如 BM25 精确。

**代码中怎么体现**：`llamaindex_tools.py:308-319`，使用 `rank_bm25.BM25Okapi`。

**面试口径**：BM25 解决的是精确匹配问题。比如"ReAct"这个专有名词，向量检索可能匹配到"reaction"或"active"，但 BM25 能精确找到含"ReAct"的文档。本项目 BM25 在向量检索的候选集上计算，不是全库扫描。如果 BM25 最高分低于 0.1，降级到纯向量。

### 4.5 WebSocket + asyncio 异步任务

**一句话解释**：WebSocket 维持长连接实时推送，asyncio 实现非阻塞后台任务。

**为什么项目需要它**：深度研究任务耗时数分钟，HTTP 不能阻塞，WebSocket 实时推送进度。

**代码中怎么体现**：`server.py:92-116` 的 `asyncio.create_task` 和 `monitor.py` 的 `ConnectionManager`。

**面试口径**：用户提交任务后，接口立即返回 thread_id，真正的 Agent 执行在后台。执行过程中的工具调用、子智能体调度、错误事件都通过 WebSocket 实时推送给前端。具体实现上，monitor 是单例，跨线程时用 asyncio.run_coroutine_threadsafe 投递到 FastAPI 的事件循环。

### 4.6 ContextVar

**一句话解释**：Python 的协程级全局变量，每个协程有自己的隔离副本。

**为什么项目需要它**：工具函数在 DeepAgents 的调用栈深处，无法逐层传递 session_dir。ContextVar 让任意深度的代码都能通过 `get_session_context()` 获取当前会话目录。

**代码中怎么体现**：`app/api/context.py`，`main_agent.py:102-103` set，`main_agent.py:195` reset。

**面试口径**：ContextVar 是 Python 标准库，和 thread-local 类似但针对协程。每个 FastAPI 请求是一个协程，在 run_deep_agent 开头 set session_dir，结尾 reset。过程中任何工具函数调用 get_session_context() 都能拿到当前会话的目录路径，不会串到其他请求。这是 ContextVar 相比传参的核心优势——不需要修改每一层函数的签名。

---

## 5. 项目主流程代码走读

### 主流程：用户提交任务 → 生成报告

**Step 1**: `POST /api/task`（`server.py:153-177`）
- 校验 query 长度 ≤ 2000
- 生成或复用 thread_id
- 取消旧的同 thread_id 任务
- `asyncio.create_task(_run_agent_with_limits(query, thread_id))` 
- 立即返回 `{"status": "started", "thread_id": "xxx"}`

**Step 2**: `run_deep_agent`（`main_agent.py:56-241`）
- 创建 `data/reports/session_{id}/` 目录
- ContextVar set：session_dir + thread_id
- 检查 `data/uploads/session_{id}/` 有上传文件 → 复制 + 注入提示
- 长期记忆检索：query 关键词匹配历史 → 拼装 memory_hint
- 拼装 path_instruction（工作目录指令）

**Step 3**: `main_agent.astream()`（`main_agent.py:154-156`）
- 输入：`{"messages": [{"role": "user", "content": query + instruction}]}`
- config：`{"configurable": {"thread_id": session_id}}`
- 异步迭代 chunk

**Step 4**: LangGraph 图循环（内部自动执行）
- LLM Node → tool_calls? → Tool Node → ToolMessage → LLM Node → ...
- subagent 调用触发 interrupt → 子图执行 → 恢复

**Step 5**: 最终结果（`main_agent.py:179-185`）
- LLM 无 tool_calls → task_result 事件
- monitor.report_task_result(last_msg.content) → WebSocket 推送

**Step 6**: 持久化（`main_agent.py:198-233`）
- 保存前 500 字到长期记忆
- 保存对话记录
- 更新会话元数据（文件数、完成状态）

**Step 7**: finally（`main_agent.py:195`）
- reset_session_context 清除 ContextVar

### 面试口头表达

> 用户提交 query，FastAPI 接口收到后先校验长度，然后生成唯一的 thread_id，通过 asyncio.create_task 把真正的 Agent 执行丢到后台协程，接口立即返回不用担心请求超时。run_deep_agent 会先创建会话目录、写入 ContextVar、检索历史记忆，然后用 main_agent.astream 驱动 LangGraph 图。图里主 LLM 负责决策，需要信息就调工具或子智能体，子智能体通过 interrupt 机制执行自己的 subgraph。LLM 觉得信息够了就生成最终回答。回答通过 WebSocket 推给前端，同时持久化到 SQLite。最后恢复 ContextVar。

---

## 6. 项目亮点提炼

### 亮点 1：一主三从多智能体编排

**简历表达**：基于 DeepAgents + LangGraph 构建 Orchestrator-Workers 架构，主 Agent 负责任务规划与多步推理，三个字典式子智能体分别处理网络搜索、数据库查询和论文库检索，通过 LangGraph interrupt 机制实现子图挂起与恢复。

**技术解释**：DeepAgents 的 `create_deep_agent` 内部创建 LangGraph StateGraph，注册 model_node、tool_node 和条件边。子智能体以字典注册，被调用时触发 interrupt 挂起主图、执行子图、恢复主图。

**面试展开**：这个架构最核心的设计是一主三从。主智能体负责"想"，三个子智能体负责"做"。子智能体的定义是字典——name、description、system_prompt、tools，路由纯靠主 LLM 通过 description 语义匹配自行决定。这比硬编码 if-else 灵活得多，加一个新的子智能体只需要新增一个字典，不改调度逻辑。

**代码依据**：`app/agent/main_agent.py:44-50`、`app/agent/subagents/*.py`

### 亮点 2：四层混合检索流水线

**简历表达**：基于 LlamaIndex 构建论文 RAG 链路，采用向量检索 → BM25 候选集评分 → RRF 融合 → MiniLM 重排序的四层流水线，MRR 从纯向量的 0.15 提升至全链路的 0.4167。

**技术解释**：向量 + BM25 + RRF 融合 + 可选 MiniLM 重排序。BM25 降级兜底，所有检索参数集中配置在 retrieval_config.py。

**面试展开**：不是单一向量检索。向量取候选后，用 rank-bm25 在同一批候选上算 BM25 分数，然后 RRF 融合。如果 BM25 完全不命中（最高分 < 0.1）则降级到纯向量。重排序用 MiniLM 计算余弦相似度，默认关闭因为加载慢，可以配置开启。所有参数集中在 retrieval_config.py，调参不用改代码。

**代码依据**：`app/tools/llamaindex_tools.py:270-370`、`app/config/retrieval_config.py`

### 亮点 3：结构化证据链与引用自动校验

**简历表达**：将检索结果结构化为标准 evidence 对象并持久化；设计引用校验模块自动提取报告中的引用标记，通过 MiniLM 语义相似度量化验证，输出覆盖率和 unfounded 率指标。

**技术解释**：evidence 包含 source/page/score/quote/metadata。Agent 用 `【证据: xxx】` 标记引用。后置校验提取标记、匹配证据、算语义相似度、分 verified/low/unfounded。

**面试展开**：RAG 不能止步于返回一段文本。每条 evidence 有来源、页码、分数和原文，前端能清晰展示。Agent 生成报告时 prompt 要求绑定证据编号，系统在后置步骤自动验证引用真实性。这样面试官问"你怎么保证引用是真的"时，我可以说"有系统自动校验，不是靠 prompt 承诺"。

**代码依据**：`app/tools/llamaindex_tools.py:233-246`、`app/tools/citation_checker.py`、`app/models/session.py:299-334`

### 亮点 4：工程化可靠性加固

**简历表达**：SQLite + WAL 事务替换 JSON 文件存储解决并发写入问题；统一 DATA_ROOT 目录收敛所有运行时数据；SQL 只读白名单 + 多语句拦截 + 路径穿越防护 + Agent 限流超时 + 健康检查接口 + 上传限制。

**技术解释**：6 项安全机制、4 项可靠性机制，每一项都是压测发现风险后加的。

**面试展开**：最初用 JSON 文件存会话，100 路并发写入发现数据丢失，换成 SQLite + WAL 事务解决。路径穿越测试发现下载接口直接拼路径，补了 resolve() + is_relative_to()。SQL 发现多语句注入可能绕过前缀检查，加了分号拦截。这些不是一次性加的，是每轮压测发现一个问题修一个，最后汇总成完整的安全体系。

**代码依据**：`app/config/paths.py`、`app/tools/db_tools.py`、`app/utils/path_utils.py`、`app/api/server.py:67-68`

---

## 7. 面试官可能深挖的问题

### 基础理解类

**问题 1：这个项目解决了什么问题？**
回答：科研人员做文献调研时，需要同时查互联网、查论文数据库、查本地论文 PDF，最后汇总成综述报告。单个大模型无法独立完成跨源、多步骤的深度调研。本项目用多智能体架构把调研流程自动化——主智能体负责规划和决策，三个专家助手分别负责不同信息源的检索，最后生成结构化报告。

**问题 2：为什么要做成 Agent 而不是简单 RAG？**
回答：简单 RAG 回答"ReAct 是什么"还行，但用户的问题是"调研影响力最大化算法的研究进展，对比 MIM-Reasoner 和 Graph Bayesian Optimization 的方法差异，生成一篇对比分析报告"。这需要规划子任务、多步检索、跨源交叉验证、结构化成文。Agent 的推理循环（think → act → observe → think）天然适合这种场景。

**问题 3：你的项目和普通 RAG 有什么区别？**
回答：第一，检索不是单路的，是向量+BM25+重排序多路融合。第二，检索结果不是纯文本，是标准化 evidence 数组，前端能逐条展示。第三，生成不是一步到位，是主智能体规划、调助手、汇总、生成的完整流程。第四，生成后引用会被自动校验真伪。

### 架构设计类

**问题 4：为什么要用 LangGraph / DeepAgents？**
回答：见 3.1.4 问题 1。

**问题 5：多 Agent 之间如何分工？**
回答：主智能体负责决策，三个子智能体只负责获取信息。子智能体互不通信，全部通过主智能体中转。分工的依据是信息源类型——网络搜索、数据库查询、本地论文库检索。

**问题 6：状态是如何传递的？**
回答：两个层面。LangGraph 层面通过 State 对象的 messages 列表传递，每条消息自动追加到历史。工程层面通过 ContextVar 传递 session_dir 和 thread_id，工具函数可以随时获取当前会话目录。

**问题 7：如果某个节点失败怎么办？**
回答：工具函数全部 try-except 返回错误字符串，不会抛异常。Agent 收到错误后会自行决定重试还是换策略。如果子智能体执行失败，结果以 ToolMessage 携带错误信息回传，主 LLM 自行判断。关键性的异常（如 CancelledError）会层层传播到 run_deep_agent 被捕获。

### RAG 检索类

**问题 8：为什么要混合检索？**
回答：向量检索擅长语义匹配，但专有名词和缩写容易误匹配。BM25 擅长关键词精确匹配，但同义词和语义泛化能力弱。两者互补。

**问题 9：BM25 和向量检索区别是什么？**
回答：BM25 基于词频统计，匹配查询词和文档词的精确重合。向量检索通过 embedding 把文本映射到语义空间，匹配的是"意思相近"的文本。举例：查询"深度学习"，BM25 只找含"深度学习"的文档，向量检索能找到含"神经网络"的文档。

**问题 10：chunk size 怎么选的？**
回答：512。太短（128）导致 chunk 语义不完整，太长（1024）单个 chunk 含多个主题降低检索精度。overlap=64 保证句子级连续性。

**问题 11：rerank 的作用是什么？**
回答：向量和 BM25 融合后返回 top_k，但排序可能不精确。rerank 用 MiniLM 对 query 和每个候选计算语义相似度，重新排序。效果好但模型加载慢，所以设计了开关。

**问题 12：如何评估检索效果？**
回答：20 条 query 的 ground truth，对比三种策略的 Recall@K 和 MRR。运行 `uv run python -m app.evaluation.evaluate --format md` 输出 Markdown 表格。

### 工程实现类

**问题 13：FastAPI 如何组织接口？**
回答：统一在 `app/api/server.py` 中。18 个 REST 接口 + 1 个 WebSocket，按功能分组：任务（submit/cancel/events）、文件（upload/download/list/knowledge）、检索（retrieval/test）和论文（cards/matrix/report）。

**问题 14：WebSocket 为什么需要？**
回答：深度研究任务耗时数分钟，HTTP 请求不能阻塞等结果。WebSocket 维持长连接，实时推送每一步的执行事件——工具调用、助手调度、任务结果。

**问题 15：后台任务如何管理？**
回答：`active_tasks: dict[str, asyncio.Task]` 管理所有活跃任务。Semaphore 控制最大 4 并发。`asyncio.wait_for` 超时 300s。同 thread_id 的新任务会先取消旧任务。

### 安全与稳定性类

**问题 16：如何防御 Prompt Injection？**
回答：没有实现完整的 prompt injection 检测，只在 fastapi middleware 层面做了基础拦截。主要的防御是：SQL 只读白名单防 SQL 注入、路径防穿越、query 长度限制。

**问题 17：如何做异常处理？**
回答：分三层。工具层：所有工具 try-except 返回用户友好的中文错误字符串。Agent 层：CancelledError 单独处理，其他异常 monitor._emit("error") 通知前端。HTTP 层：FastAPI 的 ExceptionHandler 返回 400/404。

**问题 18：如果外部搜索服务不可用怎么办？**
回答：SearXNG 不可用时，search 工具返回包含 Docker 启动指引的错误信息，不崩溃。Agent 根据错误信息自行决定是否继续。

### 项目真实性与贡献类

**问题 19：这个项目是你独立完成的吗？**
回答：项目架构设计、核心逻辑、工程化改造由我独立完成。部分代码（如 DeepAgents 示例、前端框架搭建）参考了开源项目 didilili/deepsearch-agents，在此基础上做了大量改造：搜索后端从 Tavily 换 SearXNG，知识库从 RAGFlow 换 LlamaIndex，新增证据链、引用校验、检索测试、SQLite 持久化、安全加固等。

**问题 20：哪部分最难？**
回答：引用校验模块最难。难点不在于 MiniLM 的调用，而在于定义"什么算引用可信"——不能太严格让所有引用都判 unfounded，也不能太松让编造的引用也通过。最终方案是用 evidence_id 精确匹配兜底 + MiniLM 语义相似度做额外的质量信号，阈值 0.5/0.25 是拿真实 claim 和 evidence quote 实验调出来的。

**问题 21：哪部分是 AI 帮你写的？**
回答：部分工具函数和测试代码的框架由 AI 辅助生成，但核心的业务逻辑、架构设计、异常处理策略和参数调优都是我自己做的。代码改完后我会用 compileall 和 pytest 做验证。

**问题 22：如果让你重构，你会怎么做？**
回答：第一，检索评测数据量太小（20 条），至少扩展 100+ 条。第二，引用校验的 threshold 可以自动调优而不是手写死。第三，evidence_id 换成 UUID 而不是顺序编号。第四，加上在线反馈闭环（赞/踩）收集 bad case。

---

## 8. 项目风险点与补救方案

### 风险 1：数据规模小

**面试官可能怎么问**：论文库只有 3-10 篇论文，评测只有 20 条 query，这个规模能说明问题吗？

**为什么危险**：面试官会质疑评测结果的可信度。

**应该怎么回答**：我承认数据规模偏小，当前项目的定位是验证技术方案的可⾏性，不是在百万级数据上做 benchmark。20 条 query 的评测结果证明了技术趋势——混合检索显著好于纯向量，全链路进一步提升。但如果要上线，确实需要扩展到 100+ 条 query 和更大规模的论文库。

**后续补强**：扩展 ground truth 到 100+ 条，引入公共数据集如 BEIR 做外部评测。

### 风险 2：没有真实线上用户

**面试官可能怎么问**：这个项目有真实用户在使用吗？

**为什么危险**：面试官想知道项目是否只是"课程作业"。

**应该怎么回答**：项目目前是个人独立开发的研究性质项目，没有部署到生产环境服务真实用户。但我在开发过程中做了压力测试（100 路并发写入、路径穿越测试、SQL 注入测试）来模拟真实场景的风险。如果给我机会部署上线，我有信心能快速定位和修复问题。

### 风险 3：模型只是调用 API

**面试官可能怎么问**：你做了模型微调吗？你训练过自己的模型吗？

**为什么危险**：面试官可能期待完整的模型训练链路。

**应该怎么回答**：没有做微调。本项目聚焦的是多智能体编排、RAG 检索优化和工程化可靠性。模型层面，我通过 Prompt 设计、检索增强和引用校验来提升生成质量，而不是修改模型本身。如果需要针对特定领域做微调，我认为 LoRA 是成本最低的方式。

### 风险 4：代码由 AI 辅助生成

**面试官可能怎么问**：这些代码是你自己写的吗？

**为什么危险**：面试官担心你只调 API 不理解底层原理。

**应该怎么回答**：架构设计、核心逻辑和工程化改造由我独立完成。AI 辅助了部分工具函数和测试代码的框架生成。每段代码我都理解其原理——例如为什么用 RRF 而不是加权平均、interrupt 机制如何工作、SQLite WAL 模式解决什么问题。如果面试官想深挖某个模块的实现细节，我可以详细解释。

---

## 9. 简历优化建议

### 9.1 稳妥版

> **多源论文研读与综述生成智能体** — 独立开发
>
> **技术栈**：Python、DeepAgents、LangGraph、LlamaIndex、rank-bm25、sentence-transformers、FastAPI、WebSocket、MySQL、SearXNG、SQLite、Docker
>
> **项目背景**：面向科研文献调研场景，构建多智能体论文助手，支持主题输入、多来源检索、证据聚合与 Markdown/PDF 综述导出。
>
> • 基于 DeepAgents + LangGraph 构建一主三从多智能体架构，主 Agent 负责任务规划与多步推理，子 Agent 分别处理网络搜索、数据库查询和论文库检索，通过 LangGraph interrupt 机制实现子图调度与恢复
> • 基于 LlamaIndex 构建论文 RAG 链路，采用向量召回 + BM25 候选集评分 + RRF 融合 + MiniLM 重排序的四层流水线，并构建 20 条 query 的 Recall@K 和 MRR 评测集
> • 基于 FastAPI + WebSocket 实现异步任务调度和实时进度推送，通过 ContextVar 和会话目录隔离并发任务
> • 工程化方面：SQLite + WAL 事务持久化会话/事件/证据/引用校验数据，SQL 只读白名单 + 多语句拦截 + 路径穿越防护 + Agent 限流超时 + 健康检查接口

### 9.2 强化版

> **多源论文研读与综述生成智能体** — 独立开发
>
> **技术栈**：Python、DeepAgents、LangGraph、LlamaIndex、rank-bm25、sentence-transformers、OpenAI兼容接口、FastAPI、WebSocket、asyncio、Pydantic、MySQL、SearXNG、SQLite、ReportLab、Docker
>
> **项目背景**：面向科研文献调研场景，基于多智能体架构构建论文研究助手，覆盖多源检索、证据聚合、结构化综述生成与引用校验全链路。
>
> • **多智能体编排**：基于 DeepAgents 与 LangGraph 构建"一主三从"Orchestrator-Workers 架构，主 Agent 通过 LangGraph StateGraph 运行时负责任务规划与多步推理，子 Agent 以字典式注册通过 interrupt 机制路由，上下文通过 InMemorySaver checkpoint 按 thread_id 隔离
> • **混合检索流水线**：基于 LlamaIndex 构建论文本地索引，检索采用向量召回取 top_k×2 候选，经 rank-bm25 在同一候选集上计算 BM25 分数后做 RRF 融合（k=30），最终由 MiniLM 语义重排序，MRR 从纯向量 0.15 提升至全链路 0.4167
> • **结构化证据链与引用校验**：检索结果标准化为 evidence 数组（source/page/score/quote/metadata）并持久化到 SQLite；设计引用校验模块自动提取 `【证据: xxx】` 标记，通过 MiniLM 计算 claim 与原文的语义相似度，输出覆盖率、unfounded 率等量化指标
> • **工程化可靠性**：FastAPI + WebSocket 实现异步任务调度和实时推送，跨线程通过 asyncio.run_coroutine_threadsafe 保证安全；ContextVar 隔离 session_dir 和 thread_id；SQLite + WAL 事务替代 JSON 文件存储解决并发写入一致性问题；SQL 只读白名单 + 多语句拦截 + 路径穿越防护 + Agent 限流（默认 4 并发） + 超时控制（300s） + 健康检查接口

---

## 10. 2 天速成复习路线

### 第一天：理解项目

**上午——读代码**：
1. `app/agent/main_agent.py`（最重要，理解执行入口和一主三从）
2. `app/agent/subagents/network_search_agent.py`（子智能体定义方式）
3. `app/api/server.py`（API 接口和异步调度）
4. `app/tools/llamaindex_tools.py` 的检索管线（约 270-370 行）
5. `app/tools/citation_checker.py`（引用校验流程）

**下午——理解架构**：
6. `app/config/paths.py` + `app/api/context.py`（目录和上下文管理）
7. `app/tools/db_tools.py`（SQL 安全和查询工具）
8. `app/tools/search_tool.py`（SearXNG 搜索）
9. `app/memory/memory_store.py`（长期记忆）
10. `app/models/session.py`（SQLite 全量持久化）
11. `app/evaluation/evaluate.py`（评测逻辑）

**晚上——准备口头表达**：
- 准备"项目一句话概括"
- 准备"整体架构怎么跑"的 2 分钟介绍
- 背诵亮点 1、2、3 的面试展开段落

### 第二天：面试模拟

**上午——背问答**：
- 重点背 7.1（基础理解类）+ 7.2（架构设计类）的全部问答
- 熟悉 7.4（RAG 检索类）+ 7.5（工程实现类）的关键问答应变要点

**下午——准备 Demo**：
1. 启动后端：`uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000`
2. 验证健康检查：`curl http://localhost:8000/health/live`
3. 准备检索测试：`curl -X POST ... /api/retrieval/test`
4. 准备完整任务提交流程
5. 准备引用校验 Demo

**晚上——风险防御**：
- 准备"项目真实性"的稳妥回答
- 准备"AI 辅助"的诚实回答
- 准备"如果让你重构"的改进方案
- 背熟第 8 节中所有风险点的应答

---

## 11. 面试表达禁忌

| 禁忌 | 为什么 | 正确说法 |
|------|--------|---------|
| "我训练了一个大模型" | 没做任何微调训练 | "我接入了大模型 API，通过 prompt 和 RAG 提升质量" |
| "构建了知识图谱" | 没有知识图谱 | "通过 MySQL 表和引用关系做结构化查询" |
| "实现了高并发分布式" | 单机 asyncio | "通过 asyncio + Semaphore 实现了单机并发控制" |
| "做了完整的评测系统" | 20 条 query | "构建了小规模评测集验证检索策略效果" |
| "上线了生产环境" | 未部署 | "本地开发环境，Docker Compose 一键部署" |
| "支持文本/语音/视频多模态" | 只支持文本 + 文件 | "支持文本和 PDF/Word/Excel 文件输入" |
