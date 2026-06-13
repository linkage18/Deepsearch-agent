# DeepSearch Agents — 项目架构与实现细节

> 一个面向科研文献调研的多智能体协同系统，支持知识库检索、网络搜索、结构化数据查询，自动生成 Markdown/PDF 综述报告。

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [多智能体编排层](#2-多智能体编排层)
3. [RAG 检索链路](#3-rag-检索链路)
4. [API 与实时通信](#4-api-与实时通信)
5. [记忆系统](#5-记忆系统)
6. [安全控制](#6-安全控制)
7. [前端设计](#7-前端设计)
8. [Docker 部署](#8-docker-部署)
9. [项目结构](#9-项目结构)

---

## 1. 系统架构总览

```
用户 ─→ http://localhost:8081
           │
      nginx (frontend 容器)
       ├─ /api/*  → http://backend:8000/api/*    (REST API)
       ├─ /ws/*   → http://backend:8000/ws/*     (WebSocket)
       └─ /*      → /usr/share/nginx/html         (静态文件)
                       │
                backend (FastAPI + DeepAgents)
                 ├──→ mysql:3306     (结构化元数据)
                 ├──→ searxng:8080   (自托管搜索引擎)
                 └──→ 本地磁盘        (LlamaIndex 论文库)
```

**4 个 Docker 容器：**

| 容器 | 职责 | 技术 |
|---|---|---|
| `backend` | API 服务 + Agent 执行 | FastAPI, DeepAgents, LangGraph, LlamaIndex |
| `frontend` | 静态文件 + 反向代理 | Nginx, React, Ant Design |
| `mysql` | 结构化数据存储 | MySQL 8.4 |
| `searxng` | 元搜索引擎 | SearXNG (聚合 70+ 搜索引擎) |

---

## 2. 多智能体编排层

### 2.1 "一主三从"架构

```
主智能体 (论文调研团队负责人)
├── tools: generate_markdown, convert_md_to_pdf, read_file_content
├── subagents:
│   ├── 公开学术资料搜索助手 → SearXNG 搜索
│   ├── 论文元数据查询助手  → MySQL 查询
│   └── 论文知识库研读助手  → LlamaIndex 本地库
└── checkpointer: InMemorySaver (thread_id 隔离)
```

**主智能体职责：**
1. 理解用户调研目标，制定 todo-list
2. 判断需要哪些信息来源，调度对应子智能体
3. 多来源交叉核验同一结论
4. 汇总生成 Markdown/PDF 综述

**子智能体是字典式定义（YAML 驱动）：**

```python
# app/agent/subagents/network_search_agent.py
network_search_agent = {
    "name": sub_agents_content["tavily"]["name"],
    "description": sub_agents_content["tavily"]["description"],
    "system_prompt": sub_agents_content["tavily"]["system_prompt"],
    "tools": [internet_search],  # 只需改 import 路径即可切换搜索后端
}
```

### 2.2 执行流程

```
用户提交 query
  → FastAPI 收到请求，生成 thread_id，创建后台 asyncio.Task
  → run_deep_agent() 创建会话目录，写入 ContextVar
  → 记忆系统搜索历史匹配，注入 system prompt
  → main_agent.astream() 开始异步执行
    → 模型分析任务 → 决定调用哪个子智能体
    → 子智能体通过工具获取信息 → monitor 推送事件到 WebSocket
    → 模型汇总 → 可能继续调用文件生成工具
  → 任务完成 → 保存最终结果到长期记忆
  → 前端通过 WebSocket 收到完整事件流和结果
```

### 2.3 工具与子智能体的职责分离

| 归属 | 工具 | 用途 |
|---|---|---|
| **主智能体** | `generate_markdown` | 生成 Markdown 综述文件 |
| | `convert_md_to_pdf` | Markdown → PDF 转换 |
| | `read_file_content` | 读取用户上传的附件 |
| **搜索助手** | `internet_search` | SearXNG 网络搜索 |
| **数据库助手** | `list_sql_tables` | 列出数据库表 |
| | `get_table_data` | 预览表结构和数据 |
| | `execute_sql_query` | 执行自定义 SQL |
| **知识库助手** | `list_paper_library_files` | 列出论文库文件 |
| | `search_paper_library` | 混合检索论文正文 |
| | `retrieve_paper_evidence` | 核验特定证据 |
| | `build_paper_card` | 整理论文卡片 |

### 2.4 提示词设计

提示词集中在 `app/prompt/prompts.yml` 中：

```yaml
main_agent:
  system_prompt: |
    你是一个论文研究团队负责人...
    - 先制定简短 todo-list
    - 多来源交叉核验
    - 不允许在信息不足时生成占位内容

sub_agents:
  tavily:
    name: "公开学术资料搜索助手"
    system_prompt: |
      ...
      最多进行 5 次搜索
      不要把网页摘要当作论文正文结论
```

关键设计：**子智能体 prompt 中明确告知工具列表和工作流程约束**（如"先 list_sql_tables → 再 get_table_data → 最后 execute_sql_query"），减少模型自由发挥导致的错误调用。

---

## 3. RAG 检索链路

### 3.1 检索流水线

```
query
  → LlamaIndex 向量检索 (candidate_multiplier × top_k 个候选)
    → BM25 + 向量 RRF 融合 (k=30)
      → 跨语言兜底 (BM25 max < 0.1 时降级)
        → [可选] MiniLM 语义重排序
          → 格式化返回 (含 source_type 字段)
```

### 3.2 BM25 + 向量 RRF 融合

核心算法：Reciprocal Rank Fusion

```python
rrf_score = 1.0 / (k + vector_rank) + 1.0 / (k + bm25_rank)
```

- BM25 在向量检索的候选集上计算（而非全库）
- 分词方式可配置：英文用 `split`，中文用 `jieba`
- BM25 完全无法匹配时（max < 0.1）自动降级到纯向量检索

### 3.3 Embedding 策略

三种模式通过 `.env` 切换：

```ini
# mock — 随机向量，仅用于调试
LLAMAINDEX_EMBED_MODEL=mock

# openai — 调用 OpenAI 兼容 API 做 embedding
LLAMAINDEX_EMBED_MODEL=openai
LLAMAINDEX_OPENAI_EMBED_MODEL=text-embedding-3-small

# local — 本地 sentence-transformers 模型
LLAMAINDEX_EMBED_MODEL=local
LLAMAINDEX_LOCAL_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### 3.4 Chunk 策略

```python
SentenceSplitter(chunk_size=512, chunk_overlap=64)
```

统一大小，避免大 PDF（上百 chunk）垄断召回，短文档（Markdown）至少获得 1-2 个语义完整 chunk。

### 3.5 配置收敛

所有检索参数集中在 `app/config/retrieval_config.py`：

```python
RETRIEVAL_CONFIG = {
    "rrf_k": 30,
    "enable_reranker": False,
    "rerank_model": "all-MiniLM-L6-v2",
    "candidate_multiplier": 2,
    "final_top_k": 5,
    "bm25_tokenizer": None,  # None = split, "jieba" = jieba
}
```

### 3.6 评测体系

`app/evaluation/evaluate.py` — 20 条 ground truth 的自动评测脚本：

```python
# 输出示例
Strategy             | Recall@3 | Recall@5 | MRR
纯向量               | 0.1500   | 0.1500   | 0.1500
混合(BM25+向量)      | 0.3750   | 0.3750   | 0.3917
全链路(+rerank)      | 0.4000   | 0.4500   | 0.4167
```

---

## 4. API 与实时通信

### 4.1 接口列表

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/task` | 提交调研任务 |
| POST | `/api/task/{thread_id}/cancel` | 取消任务 |
| POST | `/api/upload` | 上传会话附件 |
| POST | `/api/knowledge/upload` | 上传 PDF 到知识库 |
| GET | `/api/files?path=...` | 列出生成的文件 |
| GET | `/api/download?path=...` | 下载文件 |
| WS | `/ws/{thread_id}` | 实时事件推送 |

### 4.2 异步任务调度

```python
# app/api/server.py
@ app.post("/api/task")
async def run_task(request: TaskRequest):
    if len(request.query) > 2000:
        raise HTTPException(status_code=400)

    thread_id = request.thread_id or str(uuid.uuid4())
    # 取消同 thread_id 的旧任务
    old_task = active_tasks.get(thread_id)
    if old_task and not old_task.done():
        old_task.cancel()

    task = asyncio.create_task(run_deep_agent(request.query, thread_id))
    active_tasks[thread_id] = task
    return {"status": "started", "thread_id": thread_id}
```

### 4.3 WebSocket 事件推送

monitor 模块将工具调用、子智能体调度、异常、结果包装为标准事件格式推送到前端：

```python
# 事件格式
{
    "type": "monitor_event",
    "event": "tool_start" | "assistant_call" | "task_result" | "error" | "task_cancelled",
    "message": "开始执行工具: 网络搜索工具",
    "data": {"tool_name": "...", "args": {...}},
    "timestamp": "2026-06-07T14:27:53.738"
}
```

### 4.4 ContextVar 上下文隔离

```python
# app/api/context.py
_session_dir_ctx = ContextVar("session_dir", default=None)
_thread_id_ctx = ContextVar("thread_id", default=None)

def set_session_context(path: str) -> Token:
    return _session_dir_ctx.set(path)

def get_session_context() -> Optional[str]:
    return _session_dir_ctx.get()
```

每个异步任务开始时写入 ContextVar，结束时 reset。工具和子智能体在深层调用栈中通过 `get_session_context()` 获取当前会话目录，无需层层传参。**保证并发请求的会话隔离，避免目录串台。**

---

## 5. 记忆系统

### 5.1 设计

`app/memory/memory_store.py` — 基于 JSON 文件的轻量跨会话记忆。

```
文件: output/sessions/memory_store.json
结构: {"memories": [
  {"key": "MIM-Reasoner 摘要", "content": "...", "session_id": "xxx", "created_at": "..."},
  ...
]}
```

### 5.2 接口

```python
class MemoryStore:
    def save(self, key, content, session_id)  # 同一主题覆盖，否则追加
    def search(self, keyword)                 # 关键词子串匹配，时间降序
    def delete(self, key)                     # 按 key 删除
    def load(self)                            # 返回全部
```

### 5.3 key 重叠检测

```python
def _key_overlap(self, key1, key2) -> float:
    # 词级重叠率（非字符级）
    words1 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key1.lower()))
    words2 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key2.lower()))
    return len(words1 & words2) / max(len(words1), len(words2))
    # threshold=0.5 时 F1=0.83（实验确定）
```

### 5.4 记忆生命周期

```
任务开始 → search(query 关键词) → 匹配到历史记忆 → 注入 system prompt
任务结束 → 取最终回答前 200 字 → save(key, content, session_id)
```

**不引入向量检索、不引入额外 LLM 调用、不依赖外部存储。**

---

## 6. 安全控制

### 6.1 SQL 只读白名单

```python
# app/tools/db_tools.py
sql_upper = query.strip().upper()
if not any(sql_upper.startswith(kw) for kw in
           ("SELECT", "SHOW", "WITH", "DESCRIBE", "EXPLAIN")):
    return "拒绝执行：只允许只读查询"
```

### 6.2 Query 长度限制

```python
# app/api/server.py
if len(request.query) > 2000:
    raise HTTPException(status_code=400, detail="query 过长")
```

### 6.3 工具调用审计日志

自动写入 `output/session_{id}/tool_calls.log`：

```
2026-06-07T14:27:53|tool_start|网络搜索工具(SearXNG)
2026-06-07T14:27:58|tool_start|LlamaIndex论文库检索工具
2026-06-07T14:28:13|task_result|
```

### 6.4 路径安全

`app/utils/path_utils.py` 中的 `resolve_path()` 将模型生成的虚拟路径映射到当前会话目录，阻止路径穿越攻击。

---

## 7. 前端设计

### 7.1 Neo Kinpaku 视觉系统

从冷蓝科技风改为金箔暖黑调：

```css
/* CSS 变量变更 */
--bg: #05070b       → --bg: #1a1410       /* 冷深蓝 → 暖黑漆 */
--cyan: #20d6ff     → --gold: #d4a53a      /* 科技蓝 → 金箔金 */
--green: #5dff9f    → --verdigris: #5b8c7a /* 荧光绿 → 铜绿锈 */
--text: #eef7ff     → --text: #f0e8d8      /* 冷白 → 暖白 */
```

### 7.2 组件结构

```
App.tsx
├── 侧边栏
│   ├── 品牌标识 (KINPAKU + 金箔研搜)
│   ├── WebSocket 状态 / 助手调度 / 工具调用计数
│   ├── 智能体列表
│   ├── 知识库上传组件 (KnowledgeUpload)
│   └── API Endpoint 信息
├── 主区域
│   ├── 对话标题 + 运行状态指示器
│   ├── ConversationThread (消息流 + 事件时间线 + 文件产物)
│   └── ChatComposer (输入框 + 附件 + 发送/取消)
```

### 7.3 知识库上传

前端侧边栏直接上传 PDF 到知识库，上传后自动重建索引。上传接口：

```
POST /api/knowledge/upload  (multipart/form-data)
↓
保存到 docs/papers/
↓
调用 _load_or_build_index() 重建 LlamaIndex 索引
```

---

## 8. Docker 部署

### 8.1 容器编排

```yaml
services:
  mysql:      # MySQL 8.4 教学数据库
  backend:    # FastAPI + DeepAgents
  frontend:   # Nginx 静态文件 + 反向代理
  searxng:    # 自托管搜索引擎（零额度）
volumes:
  deepsearch_mysql_data:      # MySQL 数据持久化
  deepsearch_output:          # 会话产物持久化
  deepsearch_model_cache:     # HF 模型缓存
  deepsearch_storage:         # LlamaIndex 索引持久化
  searxng_data:               # SearXNG 配置持久化
```

### 8.2 构建优化

- `.dockerignore` 排除 `.venv/`、`node_modules/`、`.git/`，构建上下文从 500MB → **37MB**
- 单阶段 Dockerfile，避免重复拉取 base image
- 预下载 sentence-transformers 模型到镜像

### 8.3 网络拓扑

```
deepsearch-net (bridge)
  ├── backend  :8000
  ├── frontend :80 → host:8081
  ├── mysql    :3306 → host:3309
  └── searxng  :8080 → host:8888
```

服务间通过容器名通信（`mysql:3306`、`searxng:8080`），环境变量在 compose 中覆写。

---

## 9. 项目结构

```
deepsearch-agents/
├── app/
│   ├── agent/
│   │   ├── subagents/
│   │   │   ├── network_search_agent.py     # SearXNG 搜索子智能体
│   │   │   ├── database_query_agent.py     # MySQL 查询子智能体
│   │   │   └── paper_knowledge_agent.py    # 知识库研读子智能体
│   │   ├── main_agent.py                   # 主智能体组装 + 执行入口
│   │   ├── llm.py                          # LLM 模型初始化
│   │   └── prompts.py                      # YAML 提示词加载
│   ├── api/
│   │   ├── server.py                       # FastAPI 接口
│   │   ├── monitor.py                      # WebSocket 事件推送
│   │   └── context.py                      # ContextVar 上下文管理
│   ├── config/
│   │   └── retrieval_config.py             # 检索参数配置
│   ├── evaluation/
│   │   └── evaluate.py                     # 检索评测脚本
│   ├── memory/
│   │   └── memory_store.py                 # 跨会话记忆存储
│   ├── tools/
│   │   ├── search_tool.py                  # SearXNG 搜索工具
│   │   ├── db_tools.py                     # MySQL 查询工具集
│   │   ├── llamaindex_tools.py             # LlamaIndex 检索工具集
│   │   ├── rerank_tools.py                 # MiniLM 重排序工具
│   │   ├── markdown_tools.py               # Markdown 生成工具
│   │   ├── pdf_tools.py                    # PDF 转换工具
│   │   └── upload_file_read_tool.py        # 上传文件读取工具
│   ├── prompt/
│   │   └── prompts.yml                     # 提示词配置
│   └── utils/
│       ├── path_utils.py                   # 路径解析（防穿越）
│       └── word_converter.py               # Word/PDF 底层转换
├── frontend/
│   ├── src/
│   │   ├── App.tsx                         # 主页面
│   │   ├── styles.css                      # Neo Kinpaku 全局样式
│   │   ├── components/
│   │   │   ├── ChatComposer.tsx            # 输入区
│   │   │   ├── ConversationThread.tsx      # 消息流
│   │   │   ├── KnowledgeUpload.tsx         # 知识库上传面板
│   │   │   ├── AgentTopology.tsx           # 智能体拓扑
│   │   │   ├── StatusStrip.tsx             # 状态栏
│   │   │   └── MarkdownRenderer.tsx        # Markdown 渲染
│   │   ├── hooks/
│   │   │   └── useDeepAgentSession.ts      # WebSocket 会话 hooks
│   │   └── lib/
│   │       ├── api.ts                      # API 调用封装
│   │       └── config.ts                   # URL 配置
│   └── package.json
├── docker/
│   ├── docker-compose.yaml                 # 4 容器编排
│   ├── Dockerfile.backend                  # 后端镜像
│   ├── Dockerfile.frontend                 # 前端镜像
│   ├── nginx.conf                          # 反向代理配置
│   └── mysql/mysql.sql                     # 教学数据
├── docs/
│   ├── papers/                             # 知识库 PDF + Markdown
│   │   └── _ground_truth.json              # 评测数据集
│   ├── improvement_report.md               # 完整改进报告
│   └── experiment_results.json             # 实验数据
├── .env                                    # 本地环境变量
├── .env.example                            # 环境变量模板
└── .dockerignore                           # 构建上下文过滤
```

---

> **启动命令：**
> ```bash
> docker compose -f docker/docker-compose.yaml --env-file .env up -d
> ```
> 前端：http://localhost:8081  
> 后端：http://localhost:8000/docs  
> SearXNG：http://localhost:8888
