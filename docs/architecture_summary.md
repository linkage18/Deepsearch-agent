# 深度研搜项目完整架构说明

---

## 一句话说清

> 用户在浏览器输入研究课题 → FastAPI 收到请求后启动后台任务 → DeepAgents + LangGraph 驱动"一主三从"多智能体图执行 → 主智能体调度三个助手分别去搜网页、查数据库、检索论文库 → 汇总信息后生成 Markdown/PDF 报告 → 全过程通过 WebSocket 实时推送到前端。

---

## 一、完整架构分层

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                      │
│    React 前端 (Vite + Ant Design)                                        │
│    ├── 输入框提交 query → POST /api/task                                 │
│    ├── 文件上传 → POST /api/upload                                       │
│    ├── 实时进度 → WebSocket /ws/{thread_id}                              │
│    └── 产物下载 → GET /api/files + GET /api/download                     │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                         API 服务层 (FastAPI)                              │
│                                                                           │
│  server.py                                                                 │
│  ├── lifespan: 绑定事件循环到 WebSocket 管理器                            │
│  ├── POST /api/task                                                       │
│  │   ├── 接收 {"query": "调研主题", "thread_id": null}                    │
│  │   ├── 校验 len(query) ≤ 2000                                           │
│  │   ├── 生成 uuid 作为 thread_id (或复用传入的)                          │
│  │   ├── 如果已有同 thread_id 的旧任务 → 先 cancel()                     │
│  │   ├── asyncio.create_task(run_deep_agent(query, thread_id))           │
│  │   ├── task.add_done_callback(_forget_task)  // 结束后自动清理          │
│  │   └── 立即返回 {"status": "started", "thread_id": "xxx"}              │
│  ├── POST /api/task/{id}/cancel  → task.cancel()                         │
│  ├── POST /api/upload  → 保存到 updated/session_{id}/                    │
│  ├── GET /api/files → 列出 output 目录下的文件 (is_relative_to 防穿越)   │
│  ├── GET /api/download → FileResponse 流式下载                            │
│  ├── GET /api/sessions → 历史会话列表                                     │
│  ├── DELETE /api/sessions/{id} → 删除会话                                 │
│  ├── POST /api/knowledge/upload → 上传 PDF 到知识库并重建索引             │
│  └── WS /ws/{thread_id} → WebSocket 实时事件推送                          │
│                                                                           │
│  context.py                                                               │
│  ├── ContextVar("session_dir")  // 协程级全局变量                         │
│  ├── ContextVar("thread_id")                                              │
│  ├── set_session_context(path) → Token                                    │
│  ├── get_session_context() → 当前会话目录路径                             │
│  ├── get_thread_context() → 当前 thread_id                                │
│  └── reset_session_context(token) → finally 中恢复                       │
│                                                                           │
│  monitor.py                                                               │
│  ├── ToolMonitor (单例)                                                   │
│  ├── _emit(event_type, message, data)                                     │
│  │   ├── 构造 {"type":"monitor_event", "event":..., "data":..., "timestamp"} │
│  │   ├── 通过 ConnectionManager.send_to_thread 推送到前端                  │
│  │   ├── 跨线程检测: 同 loop → create_task, 不同 → run_coroutine_threadsafe│
│  │   ├── 写入 tool_calls.log 审计日志                                     │
│  │   └── 控制台保底输出 print                                             │
│  ├── report_tool(tool_name, args)     → event="tool_start"               │
│  ├── report_assistant(name, args)     → event="assistant_call"           │
│  ├── report_task_result(result)       → event="task_result"              │
│  ├── report_task_cancelled()          → event="task_cancelled"           │
│  └── report_session_dir(path)         → event="session_created"          │
│                                                                           │
│  ConnectionManager                                                        │
│  ├── active_connections: dict[thread_id → WebSocket]                      │
│  ├── set_loop(loop)  // 绑定 FastAPI 事件循环                             │
│  ├── connect(ws, thread_id) → ws.accept() + 注册                          │
│  ├── disconnect(ws, thread_id) → 只移除相同实例                           │
│  └── send_to_thread(message, thread_id) → ws.send_json()                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                      Agent 执行层 (main_agent.py)                         │
│                                                                           │
│  run_deep_agent(task_query, session_id):                                  │
│                                                                           │
│  步骤 1 ─ 初始化会话                                                      │
│  ├── save_session(session_id, query) → 写入 output/sessions/index.json    │
│  ├── 创建 output/session_{session_id}/ 工作目录                           │
│  ├── 检查 updated/session_{session_id}/ 有上传文件吗?                     │
│  │   └── 有 → shutil.copy2 复制到工作目录                                 │
│  │   └── 有 → 拼装 updated_info_prompt 告知模型有上传文件                 │
│  ├── ContextVar: set_session_context(工作目录)                            │
│  ├── ContextVar: set_thread_context(session_id)                           │
│  └── monitor.report_session_dir(工作目录)                                 │
│                                                                           │
│  步骤 2 ─ 拼装输入消息                                                    │
│  ├── path_instruction: "工作目录: output/session_xxx/..."                 │
│  │   ├── 规则1: 新文件必须保存到工作目录                                  │
│  │   ├── 规则2: 读上传文件直接用文件名, 不要加路径前缀                    │
│  │   ├── 规则3: 禁止使用绝对路径                                          │
│  │   └── 规则4: 有上传文件先分析内容                                      │
│  ├── memory_hint: query 关键词匹配历史记忆                                │
│  │   ├── re.split(r'[,，?\s]+', query) → 提取关键词                      │
│  │   ├── len(kw) < 2 → 跳过                                              │
│  │   └── memory_store.search(kw) → 匹配到就注入 system prompt            │
│  └── 最终消息: {"role":"user", "content": query + path_instruction + memory_hint} │
│                                                                           │
│  步骤 3 ─ 执行图                                                          │
│  ├── config = {"configurable": {"thread_id": session_id}}                 │
│  ├── main_agent.astream({messages: [最终消息]}, config=config)            │
│  └── 流式迭代 chunk:                                                      │
│      ├── chunk 格式: {"节点名": {"messages": [消息]}}                     │
│      ├── 检测 node_name == "model" → 检查 last_msg                        │
│      │   ├── last_msg.tool_calls 有内容?                                  │
│      │   │   ├── tool_call.name == "task" → report_assistant()            │
│      │   │   └── 其他 → report_tool()                                     │
│      │   └── last_msg.content 有内容? → report_task_result() + 存 final_result │
│      └── 异常处理: CancelledError → report_task_cancelled() + raise      │
│          Exception → monitor._emit("error", ...)                          │
│                                                                           │
│  步骤 4 ─ 清理与持久化                                                    │
│  ├── finally: reset_session_context(token, token)                         │
│  ├── 有 final_result?                                                     │
│  │   ├── 提取前 500 字 → 提取第一个 # 标题或前 30 字做 key               │
│  │   ├── memory_store.save(key, content, session_id)                     │
│  │   ├── append_turn(session_id, query, final_result[:2000])             │
│  │   └── update_session(file_count, completed=True)                      │
│  └── 打印日志                                                             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                     LangGraph 图执行引擎                                   │
│                                                                           │
│  main_agent = create_deep_agent(                                          │
│      model = llm,                          ← OpenAI 兼容接口 (Qwen)      │
│      system_prompt = "你是论文研究团队负责人...",                          │
│      tools = [generate_markdown, convert_md_to_pdf, read_file_content],  │
│      checkpointer = InMemorySaver(),        ← 按 thread_id 存上下文      │
│      subagents = [network_search_agent,                                    │
│                   database_query_agent,                                    │
│                   paper_knowledge_agent]                                   │
│  )                                                                         │
│                                                                           │
│  图结构 (DeepAgents 自动构建):                                             │
│                                                                           │
│   ┌──────────────┐                                                        │
│   │    START     │                                                        │
│   └──────┬───────┘                                                        │
│          ▼                                                                │
│   ┌──────────────┐     LLM 输出 tool_calls?                               │
│   │  model_node  │─────────────────────────────────┐                      │
│   │  (调用 LLM)   │                                  │                      │
│   └──────┬───────┘                                  │                      │
│          │ 无 tool_calls                             │ 有 tool_calls       │
│          ▼                                           ▼                     │
│   ┌──────────────┐                          ┌──────────────────┐           │
│   │    __end__   │                          │   tool_node      │           │
│   └──────────────┘                          │  (执行工具/助手)  │           │
│                                              └────────┬─────────┘           │
│                                                       │                     │
│         tool_call.name 判断:                          │                     │
│         ├── "task" → 子智能体 (interrupt 挂起主图)    │                     │
│         │   └─ 子图执行: model_node ↔ tool_node       │                     │
│         │       └─ 结果包装为 ToolMessage → 恢复主图  │                     │
│         ├── "generate_markdown" → 执行写入文件        │                     │
│         ├── "convert_md_to_pdf"  → ReportLab 转换     │                     │
│         └── "read_file_content"  → 读取上传文件       │                     │
│                                                       │                     │
│         结果 → ToolMessage → 回到 model_node          │                     │
│         └──────────────←──────────────────────────────┘                     │
│                                                                           │
│  每一步执行后: InMemorySaver.put(config, state)  // checkpoint 持久化     │
│  同一 thread_id 下次调用: InMemorySaver.get(config)  // 恢复上下文         │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
┌─────────────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  网络搜索助手        │ │ 数据库助手    │ │ 论文知识库助手       │
│                     │ │              │ │                      │
│ subagent = {        │ │ subagent = { │ │ subagent = {         │
│   name:"公开学术     │ │   name:"论文 │ │   name:"论文知识库    │
│   资料搜索助手",    │ │   元数据查询  │ │   研读助手",         │
│   tools:[           │ │   助手",     │ │   tools:[            │
│    internet_search] │ │   tools:[    │ │    search_paper_     │
│ }                   │ │   list_sql_  │ │    library,          │
│                     │ │   tables,    │ │    retrieve_paper_   │
│                     │ │   get_table_ │ │    evidence,         │
│                     │ │   data,      │ │    build_paper_card, │
│                     │ │   execute_   │ │    list_paper_       │
│                     │ │   sql_query] │ │    library_files     │
│                     │ │ }            │ │   ]                  │
│                     │ │              │ │ }                    │
└────────┬────────────┘ └──────┬───────┘ └──────────┬───────────┘
         │                    │                     │
         ▼                    ▼                     ▼
┌─────────────────┐ ┌──────────────┐ ┌─────────────────────────┐
│ SearXNG 搜索引擎 │ │ MySQL 8.4   │ │ LlamaIndex 本地论文库    │
│ GET /search     │ │ SHOW TABLES  │ │                          │
│ ?q=xxx          │ │ SELECT *     │ │ 索引: VectorStoreIndex   │
│ &format=json    │ │ FROM papers  │ │ 向量检索 → BM25 → RRF   │
│ &categories=    │ │ LIMIT 100    │ │ → MiniLM 重排序         │
│  general        │ │              │ │ → 返回证据片段          │
└─────────────────┘ └──────────────┘ └─────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                         数据源与产物层                                     │
│                                                                           │
│  ├── SearXNG: 返回 {title, url, content, engine, snippet}                │
│  ├── MySQL:   返回 CSV 格式的只读查询结果                                 │
│  ├── LlamaIndex: 返回证据块 {source_file, page, score, excerpt(900字)}   │
│  ├── 上传文件: pypdf → text / python-docx → text / pandas → head+describe │
│  └── 输出产物: output/session_{id}/.md / .pdf / .txt                     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、各模块具体实现

### 2.1 模型初始化 (app/agent/llm.py)

```python
load_dotenv(find_dotenv())   # 从当前目录向上找 .env
model = init_chat_model(
    model=os.getenv("LLM_QWEN_MAX"),    # 如 "qwen-max"
    model_provider="openai",             # OpenAI 兼容协议
)
# 通过 .env 的 OPENAI_BASE_URL + OPENAI_API_KEY 决定真实接入哪个模型
```

- 单例模式：整个项目共用一个 `model` 实例
- 通过环境变量切换模型，不改代码

### 2.2 提示词管理 (app/prompt/prompts.yml + app/agent/prompts.py)

```yaml
# prompts.yml
main_agent:
  system_prompt: |
    你是一个论文研究团队负责人，负责协调三个专家助手...
    - 先制定 todo-list
    - 多来源交叉核验
    - 不允许在信息不足时生成占位内容

sub_agents:
  tavily:
    name: "公开学术资料搜索助手"
    description: "负责查询互联网公开学术资料..."
    system_prompt: "你是一个专业的公开学术资料搜索助手..."
  db:
    name: "论文元数据查询助手"
    ...
  paper_knowledge:
    name: "论文知识库研读助手"
    ...
```

```python
# prompts.py
prompt_yaml_content = yaml.safe_load(open("prompts.yml"))
main_agent_content = prompt_yaml_content["main_agent"]
sub_agents_content = prompt_yaml_content["sub_agents"]
```

- YAML 集中管理，改提示词不用改代码
- 子智能体的 name 和 description 用于 LLM 决策是否调用

### 2.3 子智能体定义 (app/agent/subagents/*.py)

三个子智能体都是**字典**，不是独立的 LangGraph 节点：

```python
# network_search_agent.py
network_search_agent = {
    "name": sub_agents_content["tavily"]["name"],         # "公开学术资料搜索助手"
    "description": sub_agents_content["tavily"]["description"],
    "system_prompt": sub_agents_content["tavily"]["system_prompt"],
    "tools": [internet_search],                            # 只用 1 个工具
}

# database_query_agent.py
database_query_agent = {
    "name": sub_agents_content["db"]["name"],
    "description": sub_agents_content["db"]["description"],
    "system_prompt": sub_agents_content["db"]["system_prompt"],
    "tools": [list_sql_tables, get_table_data, execute_sql_query],  # 3 个工具
}

# paper_knowledge_agent.py
paper_knowledge_agent = {
    "name": sub_agents_content["paper_knowledge"]["name"],
    "description": sub_agents_content["paper_knowledge"]["description"],
    "system_prompt": sub_agents_content["paper_knowledge"]["system_prompt"],
    "tools": [list_paper_library_files, search_paper_library,
              retrieve_paper_evidence, build_paper_card],  # 4 个工具
}
```

### 2.4 主智能体组装 (app/agent/main_agent.py:44-50)

```python
main_agent = create_deep_agent(
    model=model,                               # OpenAI 兼容 LLM
    system_prompt=main_agent_content["system_prompt"],  # 来自 YAML
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],  # 主智能体直属
    checkpointer=InMemorySaver(),              # LangGraph 检查点
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)
```

### 2.5 网络搜索工具 — SearXNG (app/tools/search_tool.py)

```python
# 配置
SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://searxng:8080")

# 核心调用
url = f"{SEARXNG_BASE_URL}/search"
params = {
    "q": query,            # 搜索关键词
    "format": "json",      # 返回 JSON 格式
    "categories": category, # general / news
    "pageno": 1
}
headers = {"User-Agent": "DeepSearch-Agent/1.0"}
resp = requests.get(url, params=params, headers=headers, timeout=5)
results = resp.json().get("results", [])[:max_results]

# 解析结果
for r in results:
    item = {
        "title": r.get("title", "无标题"),
        "url": r.get("url", ""),
        "content": r.get("content", ""),
        "snippet": " ".join(content.split())[:500],  # 截断 500 字
        "source": r.get("engine", "unknown"),         # 来源引擎名
    }
```

### 2.6 数据库工具 — MySQL (app/tools/db_tools.py)

三个工具：

```python
# 1. 列出所有表
def list_sql_tables():
    with connect(**config) as conn:
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        return "可用的表有: 表1, 表2, ..."

# 2. 预览表数据 (前 100 行)
def get_table_data(table_name):
    with connect(**config) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
        # 返回 CSV: 列名行 + 数据行

# 3. 执行只读 SQL (带安全校验)
def execute_sql_query(query):
    sql_upper = query.strip().upper()
    # 白名单: 只放行 SELECT / SHOW / WITH / DESCRIBE / EXPLAIN
    if not any(sql_upper.startswith(kw) for kw in
               ("SELECT", "SHOW", "WITH", "DESCRIBE", "EXPLAIN")):
        return "拒绝执行：只允许只读查询"
    # 执行并返回 CSV 格式结果
```

### 2.7 论文知识库工具 — LlamaIndex (app/tools/llamaindex_tools.py)

**索引构建**：

```python
# 配置
PAPER_DIR = "docs/papers/"           # PDF/MD 文件目录
INDEX_DIR = "storage/paper_index/"    # 索引持久化目录
CHUNK_SIZE = 512                      # 分块大小
CHUNK_OVERLAP = 64                    # 重叠字数

# 加载文档 → 分块 → 构建索引
documents = SimpleDirectoryReader(
    input_dir=PAPER_DIR, recursive=True,
    required_exts=[".pdf", ".md", ".txt", ".docx"]
).load_data()
parser = SentenceSplitter(chunk_size=512, chunk_overlap=64)
nodes = parser(documents)
index = VectorStoreIndex(nodes)
index.storage_context.persist(persist_dir=INDEX_DIR)

# Embedding 可切换 (通过 .env):
#   LLAMAINDEX_EMBED_MODEL=mock      → MockEmbedding(384)  // 调试用
#   LLAMAINDEX_EMBED_MODEL=openai    → OpenAIEmbedding("text-embedding-3-small")
#   LLAMAINDEX_EMBED_MODEL=local     → HuggingFaceEmbedding("all-MiniLM-L6-v2")
```

**检索流水线** (`search_paper_library` 工具)：

```python
# 1. 向量检索候选
candidate_k = max(1, min(top_k * 2, 20))        # 取 top_k×2 候选
retriever = index.as_retriever(similarity_top_k=candidate_k)
vector_nodes = retriever.retrieve(query)

# 2. BM25 在同一候选集上计算
tokenizer = str.split if config.bm25_tokenizer is None else jieba.cut
tokenized_corpus = [tokenizer(n.text) for n in vector_nodes]
tokenized_query = tokenizer(query)
bm25 = BM25Okapi(tokenized_corpus)
bm25_scores = bm25.get_scores(tokenized_query)

# BM25 降级: 如果 max(bm25_scores) < 0.1, 纯向量
if max(bm25_scores) < 0.1:
    fused_nodes = vector_nodes  # 降级
else:
    # 3. RRF 融合
    rrf_k = 30
    scored = []
    for rank, node in enumerate(vector_nodes):
        vector_rank = rank
        bm25_rank = bm25_rank_of_node
        rrf_score = 1.0 / (rrf_k + vector_rank) + 1.0 / (rrf_k + bm25_rank)
        scored.append((rrf_score, node))
    scored.sort(reverse=True)  # rrf_score 降序
    fused_nodes = [node for _, node in scored]

# 4. [可选] MiniLM 重排序
if config.enable_reranker:
    from rerank_tools import rerank_candidates
    fused_nodes = rerank_candidates(query, fused_nodes, top_k=top_k)
    # all-MiniLM-L6-v2 encode(query) · encode(docs) → cosine similarity

# 5. 取 top_k 返回
final = fused_nodes[:top_k]
# 格式化: 来源文件 | 页码 | 分数 | 内容节选(900字)
```

### 2.8 文件生成工具

**Markdown** (`app/tools/markdown_tools.py`)：

```python
def generate_markdown(content: str, filename: str, path: str = ""):
    if not filename.endswith(".md"):
        filename += ".md"
    full_path = resolve_path(f"{path}/{filename}", session_dir)
    file_path.write_text(content, encoding="utf-8")
    return f"文件已生成: {filename}"
```

**PDF** (`app/tools/pdf_tools.py` + `word_converter.py`)：

```python
def convert_md_to_pdf(md_filename, pdf_filename=None):
    md_path = resolve_path(md_filename, session_dir)
    pdf_path = md_path.with_suffix(".pdf") if not pdf_filename else ...
    # 调用 convert_md_to_pdf_via_word()
    # 内部使用 ReportLab:
    #   - pageSize = A4
    #   - margins = 2cm
    #   - 中文字体: STSong-Light
    #   - 解析 Markdown: # → H1, ## → H2, ``` → code block, | → table
    #   - 构建 ReportLab Story → SimpleDocTemplate.build(story)
```

**上传文件读取** (`app/tools/upload_file_read_tool.py`)：

```python
def read_file_content(filename, instruction="提取全部内容"):
    file_path = resolve_path(filename, session_dir)
    if suffix == ".md" or suffix == ".txt":
        return file_path.read_text(encoding="utf-8")
    elif suffix == ".docx":
        doc = docx.Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    elif suffix == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join([page.extract_text() for page in reader.pages])
    elif suffix == ".xlsx" or suffix == ".xls":
        df = pd.read_excel(file_path)
        return f"行数:{len(df)} 列数:{len(df.columns)}\n列名:{df.columns}\n{df.head()}"
```

### 2.9 长期记忆 (app/memory/memory_store.py)

```python
# 数据结构
{
    "key": "影响力最大化算法研究",      # 第一个 # 标题或 query 前 30 字
    "content": "前 500 字...",           # 结果前 500 字
    "session_id": "xxx",
    "created_at": "2026-06-11T...",
    "updated_at": "2026-06-11T..."
}

# 存储: output/sessions/memory_store.json, 最多 50 条

# 保存
def save(key, content, session_id):
    for mem in self._memories:
        if _key_overlap(key, mem["key"]) >= 0.5:
            mem["content"] = content  # 覆盖
            return
    self._memories.append({...})      # 追加

# 搜索 (关键词子串匹配)
def search(keyword):
    matches = [m for m in self._memories
               if keyword.lower() in m["key"].lower()
               or keyword.lower() in m["content"].lower()]
    return sorted(matches, key=lambda m: m.get("updated_at"), reverse=True)

# 词级重叠率 (判断是否同一主题)
def _key_overlap(key1, key2):
    words1 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key1.lower()))
    words2 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key2.lower()))
    return len(words1 & words2) / max(len(words1), len(words2))
```

### 2.10 会话元数据 (app/models/session.py)

```python
# 存储: output/sessions/index.json
# 结构:
{
    "sessions": [{
        "id": "session_xxx",
        "title": "query 前 30 字...",
        "created_at": "...",
        "updated_at": "...",
        "file_count": 2,
        "completed": True,
        "turns": [{"query": "...", "result": "..."}]  # 最多 20 轮
    }]
}
```

---

## 三、完整数据流

### 3.1 请求进入

```
用户浏览器
  │
  ├── 用户在输入框输入: "调研影响力最大化算法的最新研究进展"
  │
  ├── POST /api/task
  │   Body: {"query": "调研影响力最大化算法的最新研究进展", "thread_id": null}
  │
  ├── server.py:
  │   ├── len(query)=20 → ≤2000, 通过
  │   ├── thread_id = uuid.uuid4() → "a1b2c3d4-e5f6-..."
  │   ├── old_task = None (新会话)
  │   ├── task = asyncio.create_task(run_deep_agent(query, thread_id))
  │   └── return {"status": "started", "thread_id": "a1b2c3d4-e5f6-..."}
  │
  └── 前端同时打开 WS /ws/a1b2c3d4-e5f6-...
```

### 3.2 Agent 执行

```
run_deep_agent("调研影响力最大化算法的最新研究进展", "a1b2c3d4-e5f6-...")

├── 初始化
│   ├── save_session → index.json 写入新记录
│   ├── mkdir output/session_a1b2c3d4-e5f6-.../
│   ├── updated/ 没有文件 → 跳过
│   ├── ContextVar: set_session_context("output/session_a1b2c3d4-e5f6-...")
│   ├── ContextVar: set_thread_context("a1b2c3d4-e5f6-...")
│   └── monitor.report_session_dir(...) → WS 推送 session_created
│
├── 拼装消息
│   ├── path_instruction: "工作目录: output/session_a1b2c3d4-e5f6-..."
│   ├── memory_hint: 搜索历史 → 无匹配 → 空
│   └── user_message = query + path_instruction
│
├── 图执行 (astream)
│   │
│   ├── Step 1: model_node
│   │   └── LLM 收到: "调研影响力最大化算法的最新研究进展" + 工作目录指令
│   │   └── LLM 输出: AIMessage(
│   │       content="我来分析这个任务，需要先搜索公开资料...",
│   │       tool_calls=[{
│   │           "name": "task",
│   │           "args": {
│   │               "subagent_type": "network_search_agent",
│   │               "description": "搜索影响力最大化的最新研究"
│   │           }
│   │       }]
│   │   )
│   │   └── monitor: 检测到 tool_call[0].name == "task"
│   │       → report_assistant("公开学术资料搜索助手") → WS 推送 assistant_call
│   │
│   ├── Step 2: task (子智能体)
│   │   ├── DeepAgents 拦截 task 调用
│   │   ├── interrupt 挂起主图, 保存 checkpoint
│   │   ├── 启动子智能体: "公开学术资料搜索助手" (自己的 system_prompt + tools)
│   │   │
│   │   │   ├── 子 Step 1: internet_search(query="影响力最大化 2024 2025")
│   │   │   │   ├── GET http://searxng:8080/search?q=影响力最大化&format=json
│   │   │   │   ├── 返回: [{title, url, content, engine}, ...]
│   │   │   │   └── monitor.report_tool("internet_search") → WS 推送 tool_start
│   │   │   │
│   │   │   ├── 子 Step 2: internet_search(query="Influence Maximization survey")
│   │   │   │   └── ...
│   │   │   │
│   │   │   └── 子 Step 3: 总结搜索结果 → 返回 ToolMessage
│   │   │
│   │   ├── 子智能体完成
│   │   └── 恢复主图, 结果注入 state
│   │
│   ├── Step 3: model_node (收到搜索结果)
│   │   └── LLM: "搜索结果找到了几篇相关论文，需要去论文库查正文..."
│   │   └── tool_calls=[{name: "task", args: {subagent_type: "paper_knowledge_agent"}}]
│   │   └── monitor.report_assistant("论文知识库研读助手") → WS 推送
│   │
│   ├── Step 4: task (论文库子智能体)
│   │   ├── interrupt 挂起 → 启动论文库助手
│   │   │
│   │   │   ├── search_paper_library(query="Influence Maximization", top_k=5)
│   │   │   │   ├── 向量检索: index.as_retriever(10).retrieve(query)
│   │   │   │   ├── BM25: BM25Okapi(tokenized_corpus).get_scores(tokenized_query)
│   │   │   │   ├── RRF: score = 1/(30+vec_rank) + 1/(30+bm25_rank)
│   │   │   │   ├── MiniLM: model.encode(query)·model.encode(docs) → cosine
│   │   │   │   └── 返回 top 5 证据块 {source, page, score, excerpt}
│   │   │   │
│   │   │   ├── retrieve_paper_evidence(claim="MIM-Reasoner 使用强化学习")
│   │   │   │   └── 针对性地检索证据
│   │   │   │
│   │   │   └── 汇总 → 返回 ToolMessage(证据内容)
│   │   │
│   │   └── 恢复主图
│   │
│   ├── Step 5: model_node (收到论文证据)
│   │   └── LLM: "信息已经足够，可以生成报告了..."
│   │   └── tool_calls=[{
│   │       "name": "generate_markdown",
│   │       "args": {
│   │           "filename": "影响力最大化调研报告",
│   │           "content": "# 影响力最大化算法调研\n\n## 研究背景..."
│   │       }
│   │   }]
│   │   └── monitor.report_tool("generate_markdown") → WS 推送
│   │
│   ├── Step 6: tool_node
│   │   └── generate_markdown(content, filename)
│   │       └── write_text("output/session_a1b2c3d4/影响力最大化调研报告.md")
│   │       └── 返回 ToolMessage("文件已生成: 影响力最大化调研报告.md")
│   │
│   ├── Step 7: model_node
│   │   └── LLM: "报告已生成，是否需要转为 PDF?"
│   │   └── tool_calls=[{
│   │       "name": "convert_md_to_pdf",
│   │       "args": {"md_filename": "影响力最大化调研报告.md"}
│   │   }]
│   │   └── monitor.report_tool("convert_md_to_pdf") → WS 推送
│   │
│   ├── Step 8: tool_node
│   │   └── convert_md_to_pdf("影响力最大化调研报告.md")
│   │       └── ReportLab: 解析 Markdown → 构建 Story → build PDF
│   │       └── 返回 ToolMessage("PDF 已生成: 影响力最大化调研报告.pdf")
│   │
│   ├── Step 9: model_node
│   │   └── LLM: 无 tool_calls, 只有 content
│   │   └── AIMessage(content="已完成调研报告，生成了 MD 和 PDF 文件...")
│   │   └── monitor.report_task_result(content) → WS 推送 task_result
│   │   └── final_result = content
│   │
│   └── → __end__ (图执行结束)
│
└── 清理与持久化
    ├── reset_session_context(token, token)  // 恢复 ContextVar
    ├── final_result 不为空:
    │   ├── content_trimmed = final_result[:500]
    │   ├── memory_key = "# 影响力最大化算法调研"  (提取第一个 h1)
    │   ├── memory_store.save(memory_key, content_trimmed, session_id)
    │   ├── append_turn(session_id, query, final_result[:2000])
    │   ├── file_count = 扫描 output/session/ 下 .md/.pdf 文件数
    │   └── update_session(session_id, completed=True, file_count=2)
    └── 打印日志
```

### 3.3 输出产物

```
# 工作目录
output/session_a1b2c3d4-e5f6/
  ├── 影响力最大化调研报告.md          # generate_markdown 生成
  ├── 影响力最大化调研报告.pdf          # convert_md_to_pdf 转换
  └── tool_calls.log                   # monitor 写入的审计日志
       # 内容:
       2026-06-11T14:27:53|tool_start|internet_search
       2026-06-11T14:27:58|assistant_call|公开学术资料搜索助手
       2026-06-11T14:28:13|tool_start|search_paper_library
       2026-06-11T14:28:18|tool_start|generate_markdown
       2026-06-11T14:28:22|tool_start|convert_md_to_pdf
       2026-06-11T14:28:25|task_result|

# 全局数据
output/sessions/
  ├── index.json                        # 会话索引 (所有会话元数据)
  └── memory_store.json                 # 长期记忆 (最多 50 条)
```

### 3.4 前端同时收到的 WebSocket 事件流

```
← {"event": "session_created", "data": {"path": "output/session_a1b2c3d4..."}}
← {"event": "assistant_call", "data": {"assistant_name": "公开学术资料搜索助手"}}
← {"event": "tool_start", "data": {"tool_name": "internet_search"}}
← {"event": "tool_start", "data": {"tool_name": "internet_search"}}
← {"event": "assistant_call", "data": {"assistant_name": "论文知识库研读助手"}}
← {"event": "tool_start", "data": {"tool_name": "search_paper_library"}}
← {"event": "tool_start", "data": {"tool_name": "retrieve_paper_evidence"}}
← {"event": "tool_start", "data": {"tool_name": "generate_markdown"}}
← {"event": "tool_start", "data": {"tool_name": "convert_md_to_pdf"}}
← {"event": "task_result", "data": {"result": "已完成调研报告..."}}
```

### 3.5 用户后续操作

```
1. 前端展示最终回答 + 文件列表
2. 用户点击"影响力最大化调研报告.pdf" → GET /api/download?path=... → FileResponse
3. 用户再问:"详细说明 MIM-Reasoner 的方法"
   → POST /api/task {"query": "...", "thread_id": "a1b2c3d4-e5f6-..."}
   → InMemorySaver.get(config) 恢复历史上下文
   → Agent 在已有讨论基础上继续
4. 用户上传一篇 PDF → POST /api/upload → saved to updated/session_a1b2c3d4/
   → 下次任务自动复制到工作目录 + 提示模型读取
```

---

## 四、架构核心设计要点

| 要点 | 怎么做的 | 为什么 |
|------|---------|--------|
| 用户提交任务不阻塞 | `asyncio.create_task` 后台执行, 接口立即返回 | 深度研究可能耗时数分钟 |
| 并发请求不串台 | ContextVar 隔离每个协程的 session_dir + thread_id | 避免文件写到别人的目录 |
| 同一会话任务替换 | 新任务先 cancel 旧任务 | 避免同名目录被两个任务同时写 |
| 子智能体不污染主图 | interrupt 挂起 + 独立 subgraph + ToolMessage 回传 | 每个助手有自己的 prompt 和工具 |
| 多轮对话 | InMemorySaver 按 thread_id 存 checkpoint | 第二轮自动恢复上下文 |
| 文件安全 | resolve() + is_relative_to() | 防 ../ 穿越到系统目录 |
| SQL 安全 | 白名单只放行 SELECT/SHOW/WITH/DESCRIBE/EXPLAIN | 防 AI 误写或恶意注入 |
| 检索质量 | 向量 + BM25 + RRF + MiniLM 四层 | MRR 从 0.61 提升到 0.89 |
| 记忆不依赖外部存储 | JSON 文件 + 关键词匹配 | 简化部署, ≤50 条足够高效 |
| 搜索不依赖付费 API | SearXNG 自托管 | 零费用, 可自选引擎 |

---

## 五、一句话总结

> **FastAPI 接收 query → asyncio.create_task 后台执行 → DeepAgents + LangGraph 驱动一主三从图 → 主智能体通过 LLM 决策调度三个子智能体 → 子智能体分别调 SearXNG 搜网页 / MySQL 查元数据 / LlamaIndex+BM25+RRF+MiniLM 检索论文 → 主智能体汇总后调用 generate_markdown / convert_md_to_pdf 生成文件 → 全过程 monitor 通过 WebSocket 推事件到前端 → 任务结束存记忆到 JSON → 前端下载产物。**
