<div align='center'>
  <h1 style="margin-top: 15px;">深度研搜 · 多智能体论文研究系统</h1>
  <h4><b>deepsearch-agents</b></h4>
  <p><em>基于 DeepAgents + LangGraph + FastAPI + React 的多智能体学术论文深度研究系统，支持多来源检索、RAG 增强生成、实时可观测执行链路与自动报告交付</em></p>
</div>

<div align='center'>

![AI](https://img.shields.io/badge/AI-Agent-00c853?style=flat)
![DeepAgents](https://img.shields.io/badge/DeepAgents-0.5.7-1C3C3C.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-009688.svg?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

</div>

> **本项目基于 [didilili/deepsearch-agents](https://github.com/didilili/deepsearch-agents) 进行二次开发，在原有一主三从多智能体架构基础上进行了深度改造与增强。**

## 项目介绍

在真实的学术研究场景中，文献调研往往需要同时检索多个信息源：互联网公开论文页面与 arXiv、结构化论文元数据库（标题、作者、会议、引用关系）、本地论文 PDF 知识库。单个大模型无法独立完成这类跨源、多步骤的深度调研任务。

本项目基于 DeepAgents 的 Orchestrator-Workers 模式，构建了一套**面向学术论文研究的对话式多智能体系统**：

```text
用户提交调研课题
  -> 主智能体理解任务、制定 todo-list
  -> 调度三个专家助手分别获取信息
    -> 公开学术资料搜索助手（SearXNG 自托管搜索引擎）
    -> 论文元数据查询助手（MySQL 结构化数据）
    -> 论文知识库研读助手（LlamaIndex 本地索引 + BM25 + 重排序）
  -> 主智能体交叉核验、汇总信息
  -> 调用文件工具生成 Markdown / PDF 综述报告
  -> 前端实时展示执行过程和交付产物
```

## 与原版的差异

本项目在原始 deepsearch-agents 基础上做了以下核心改造：

| 维度 | 原版 | 本版 |
|------|------|------|
| **搜索后端** | Tavily（付费 API） | SearXNG（自托管，零费用） |
| **知识库** | RAGFlow（外部服务） | LlamaIndex（本地索引，自包含） |
| **应用领域** | 通用行业研究 | 学术论文文献综述 |
| **检索流水线** | 无 | 向量 + BM25 RRF 融合 + MiniLM 重排序 |
| **跨会话记忆** | 无 | 基于 JSON 的关键词匹配长期记忆 |
| **会话管理** | 无 | 完整 CRUD、对话轮次持久化、历史回顾 |
| **容器化** | 仅 MySQL | 4 容器编排（MySQL + Backend + Frontend + SearXNG） |
| **前端主题** | 冷蓝科技风 | Neo Kinpaku（金箔）暖黑金配色 |
| **知识库上传** | 无 | 前端 PDF 上传 + 自动索引重建 |
| **审计日志** | 无 | 工具调用自动写入日志文件 |
| **检索评测** | 无 | 内置评测脚本，MRR 从 0.61 提升至 0.89 |
| **CI 工具链** | 无 | Pre-commit hooks、VS Code 配置、集成测试 |

## 系统架构

![系统架构图](docs/images/deepsearch-system-architecture.svg)

### 一主三从的多智能体架构

| 归属 | 能力 | 工具 |
|------|------|------|
| 主智能体 | 任务规划、助手调度、结果汇总、文件交付 | `generate_markdown`、`convert_md_to_pdf`、`read_file_content` |
| 公开学术资料搜索助手 | 查询 arXiv、论文主页、GitHub、技术博客 | `internet_search`（SearXNG） |
| 论文元数据查询助手 | 查询 MySQL 论文结构化数据 | `list_sql_tables`、`get_table_data`、`execute_sql_query` |
| 论文知识库研读助手 | 查询本地 LlamaIndex 论文库 | `search_paper_library`、`retrieve_paper_evidence`、`build_paper_card` |

### RAG 检索流水线

```
用户查询
  -> LlamaIndex 向量检索（top_k * 3 候选）
    -> BM25 + 向量 RRF 融合（k=30）
      -> 跨语言兜底（BM25 max < 0.1 时降级）
        -> [可选] MiniLM 语义重排序
          -> 格式化返回（含 source_type 字段）
```

| Strategy | Recall@3 | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| 纯向量 | 1.0000 | 1.0000 | 1.0000 | 0.6111 |
| 混合(BM25+向量) | 0.8889 | 0.8889 | 1.0000 | 0.8056 |
| 全链路(+rerank) | 1.0000 | 1.0000 | 1.0000 | **0.8889** |

### 执行流程

```
用户提交 query
  -> FastAPI 生成 thread_id，创建后台 asyncio.Task
  -> run_deep_agent() 创建会话目录，写入 ContextVar
  -> 记忆系统搜索历史匹配，注入 system prompt
  -> main_agent.astream() 开始异步执行
    -> 模型分析任务 -> 决定调用哪个子智能体
    -> 子智能体通过工具获取信息 -> monitor 推送事件到 WebSocket
    -> 模型汇总 -> 可能继续调用文件生成工具
  -> 任务完成 -> 保存最终结果到长期记忆
  -> 前端收到完整事件流和产物文件
```

## 项目技术栈

| 模块 | 技术 | 作用 |
|------|------|------|
| 智能体框架 | `DeepAgents` | 主智能体和子智能体创建、长任务调度 |
| 图与检查点 | `LangGraph` | 底层运行时和 InMemorySaver 会话检查点 |
| 模型与工具抽象 | `LangChain` / `langchain-core` | OpenAI 兼容模型封装、工具声明 |
| 大模型接入 | OpenAI 兼容接口 | 通过 `.env` 配置 base_url / api_key / model |
| 搜索引擎 | `SearXNG`（自托管） | 公开学术资料检索，零费用、零额度限制 |
| 结构化数据 | `MySQL` 8.4 | 论文元数据存储（标题、作者、引用等） |
| 知识库索引 | `LlamaIndex` | 本地论文 PDF 向量化索引 |
| 向量检索 | `Qdrant`（LlamaIndex 内置） | 论文片段向量召回 |
| 重排序 | `sentence-transformers` | MiniLM 语义重排序 |
| 文件处理 | `pypdf` / `python-docx` / `ReportLab` | 上传文件读取、Markdown 生成、PDF 转换 |
| 后端接口 | `FastAPI` / `Uvicorn` | 任务、上传、文件、WebSocket 接口 |
| 实时通信 | `WebSocket` | 工具调用、助手调度、结果和异常推送 |
| 前端 | `React` / `Vite` / `Ant Design` | 对话式研搜界面、事件流、附件上传 |
| 容器化 | `Docker` / `Docker Compose` | 4 容器一键部署 |

## 快速开始

### 环境要求

- Python 3.12
- `uv`
- Docker & Docker Compose
- Node.js & `pnpm`
- 可用的大模型 API Key（OpenAI 兼容接口）

### 启动

```bash
# 1. 克隆并安装后端依赖
git clone https://github.com/linkage18/Deepsearch-agent.git
cd deepsearch-agents
uv sync

# 2. 配置环境变量
cp .env.example .env
# 按需修改 .env 中的 LLM、MySQL、SearXNG 配置

# 3. 启动 MySQL + SearXNG
docker compose -f docker/docker-compose.yaml up -d

# 4. 启动后端
uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload

# 5. 启动前端
cd frontend
pnpm install
pnpm dev
```

### API 接口

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/task` | 提交调研任务 |
| POST | `/api/task/{thread_id}/cancel` | 取消任务 |
| POST | `/api/upload` | 上传会话附件 |
| POST | `/api/knowledge/upload` | 上传 PDF 到知识库 |
| GET | `/api/files?path=...` | 列出生成文件 |
| GET | `/api/download?path=...` | 下载文件 |
| WS | `/ws/{thread_id}` | 实时事件推送 |
| GET | `/api/sessions` | 历史会话列表 |
| GET | `/api/sessions/{id}` | 会话详情（含产物文件） |

## 项目结构

```
deepsearch-agents/
├── app/
│   ├── agent/              # 主智能体、子智能体、LLM、prompts
│   │   └── subagents/      # 网络搜索、数据库、论文知识库助手
│   ├── api/                # FastAPI 接口、WebSocket、ContextVar
│   ├── config/             # 检索参数配置
│   ├── evaluation/         # 检索评测脚本
│   ├── memory/             # 跨会话长期记忆
│   ├── models/             # 会话元数据模型
│   ├── prompt/             # 智能体提示词配置
│   ├── tools/              # 搜索、数据库、LLamaIndex、文件工具
│   └── utils/              # 路径安全、文件转换工具
├── docker/                 # Docker Compose + 容器镜像
├── docs/                   # 架构文档、评测报告、知识库 PDF
├── examples/               # DeepAgents 学习示例
├── frontend/               # React + Vite 前端
├── .env.example            # 环境变量模板
└── pyproject.toml          # 项目依赖
```

## 安全控制

- **SQL 只读白名单**：仅放行 `SELECT` / `SHOW` / `WITH` / `DESCRIBE` / `EXPLAIN`
- **Query 长度限制**：最多 2000 字符，防止 token 耗尽攻击
- **路径安全**：`resolve_path()` 阻止路径穿越攻击
- **审计日志**：每个会话的工具调用自动写入 `tool_calls.log`

## 能力边界

本项目面向学术论文研究场景，覆盖 DeepAgents 多智能体调度、真实工具接入、RAG 流水线、文件交付、WebSocket 实时推送和前后端联调。以下能力不在当前范围：

- 用户登录、角色权限和多租户隔离
- 文件安全扫描和内容审核
- 任务队列、分布式执行和大规模并发治理
- 全量事件持久化和历史会话恢复
- 系统化评测集和自动化 Agent 质量评估
- 生产监控、告警和链路追踪

## License

MIT
