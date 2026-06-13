# PRD：深度研搜 — 对话式多智能体深度研究系统

## 背景与问题

在真实研究场景中，用户的问题往往不是一句简单的问答就能解决的。例如「结合公开资料、数据库信息和我上传的文档，整理一份机器人行业研究报告，并生成 PDF」，背后涉及：判断需要哪些信息来源、检索互联网最新资料、查询结构化数据库、访问内部知识库、读取用户上传附件、汇总多来源信息、最终生成可交付文档等一系列步骤。

现有方案存在以下痛点：
- **单模型问答**：大模型仅依靠自身知识，无法获取实时、结构化和私域信息，容易产生幻觉。
- **单一检索方案**：只接入搜索 API 做演示级问答，不具备多来源交叉验证能力。
- **不可观察的长任务**：深度研究任务执行时间长，用户无法感知进度，体验差。
- **缺乏工程闭环**：停留在 Prompt 设计层面，缺少文件交付、实时推送、前后端联动的完整链路。

本项目「深度研搜」旨在通过多智能体架构，将研究任务拆解、分派、执行、汇总、交付全链路工程化，打造一个真正可用的对话式深度研究助手。

## 目标与成功指标

- **目标**：
  - 构建基于 DeepAgents 的一主三从多智能体深度研究系统，覆盖任务规划、多源检索、文件读取、报告生成与 PDF 交付全链路。
  - 提供前端实时可观察的执行过程，支持文件上传、WebSocket 事件推送、会话管理和文件下载。
  - 配套完整教程与章节 Git 分支，降低 DeepAgents 学习曲线。

- **成功指标**：
  - 多源检索正确调度率：用户任务中涉及多信息源时，主智能体正确调度对应子智能体的成功率 ≥ 90%。
  - 端到端任务完成率：从用户提交任务到生成 Markdown/PDF 的全链路成功率 ≥ 85%。
  - 检索质量 MRR（Mean Reciprocal Rank）：全链路（向量 + BM25 + 重排序）MRR ≥ 0.80。
  - WebSocket 事件推送延迟：从工具调用到前端收到推送的平均延迟 < 500ms。
  - SQL 注入拦截率：对非只读 SQL（DROP/DELETE/INSERT 等）的拦截成功率 100%。

## 用户与场景

- **目标用户**：
  - 正在学习 DeepAgents / AI Agent 工程开发的开发者
  - 需要多智能体实战项目作为简历亮点和面试素材的求职者
  - 对多来源深度研究有需求的科研人员和行业分析师

- **核心场景**：
  1. **多来源研究报告生成**：用户提交研究课题，系统自动从互联网、数据库、知识库检索资料，汇总生成 Markdown/PDF 报告。
  2. **私有知识库问答**：用户上传企业内部文档（PDF/Word/Excel），系统读取并基于上传文件回答问题或生成摘要。
  3. **结构化数据查询与汇报**：用户查询业务数据库（如库存、销售数据），系统执行只读 SQL 查询并以 Markdown 报告形式返回结果。

## 功能需求

| ID | 描述 | 优先级 |
|----|------|--------|
| R1 | 作为 用户，我希望 提交一项研究任务，以便 系统为我自动收集多来源信息并生成报告 | P0 |
| R2 | 作为 用户，我希望 系统在任务执行过程中通过 WebSocket 实时推送进度和工具调用事件，以便 我了解当前执行状态 | P0 |
| R3 | 作为 用户，我希望 上传 PDF/Word/Excel/Markdown/文本文件供系统读取，以便 系统结合我的文件内容回答问题 | P0 |
| R4 | 作为 用户，我希望 系统能从互联网公开资料（Tavily）检索最新信息，以便 获取实时、公开的研究资料 | P0 |
| R5 | 作为 用户，我希望 系统能查询 MySQL 数据库中的结构化数据，以便 获取业务数据并用于分析 | P0 |
| R6 | 作为 用户，我希望 系统能查询 RAGFlow / LlamaIndex 内部知识库，以便 获取企业私域文档中的内容 | P1 |
| R7 | 作为 用户，我希望 系统能生成 Markdown 格式的研究报告并支持下载，以便 我获得可编辑的交付物 | P0 |
| R8 | 作为 用户，我希望 系统能将 Markdown 报告转换为 PDF 文件，以便 我获得可直接分享和打印的格式 | P1 |
| R9 | 作为 用户，我希望 能查看和下载当前会话及历史会话中生成的文件，以便 回溯和复用研究成果 | P1 |
| R10 | 作为 用户，我希望 能取消正在执行的任务，以便 在任务不符合预期时及时终止 | P1 |
| R11 | 作为 用户，我希望 同一会话支持多轮对话上下文延续，以便 我在前一轮结果基础上继续追问 | P2 |
| R12 | 作为 用户，我希望 系统能记住历史会话的关键内容，以便 后续任务可参考之前的结论 | P2 |
| R13 | 作为 管理员，我希望 系统对 SQL 查询做只读白名单校验，以便 防止数据被意外写入或删除 | P0 |
| R14 | 作为 开发者，我希望 系统提供可配置的检索参数（向量模型、RRF 融合、重排序等），以便 调优检索质量 | P2 |

## 范围与边界

- **In scope**：
  - 一主三从多智能体架构（主智能体 + 网络搜索助手 + 数据库查询助手 + 知识库研读助手）
  - 多来源信息检索（Tavily 互联网搜索、MySQL 结构化数据、RAGFlow/LlamaIndex 私有知识库）
  - 上传文件读取（PDF / Word / Excel / Markdown / 纯文本）
  - Markdown 与 PDF 文件生成与交付
  - FastAPI 后端接口（任务提交/取消、文件上传/下载/列表、WebSocket 实时推送）
  - React + Vite + Ant Design 前端界面
  - 会话级上下文隔离（ContextVar + thread_id）
  - 跨会话轻量长期记忆（关键词匹配 + JSON 文件存储）
  - RAG 检索流水线（向量 + BM25 RRF 融合 + MiniLM 重排序）
  - SQL 只读白名单安全校验
  - 工具调用审计日志
  - Query 长度安全限制（2000 字符）
  - Docker Compose 一键部署（MySQL + backend + frontend + SearXNG）

- **Out of scope**：
  - 用户登录、角色权限和多租户隔离
  - 文件上传安全扫描和内容审核
  - 任务队列、分布式执行和大规模并发治理
  - 全量事件持久化、历史会话完整恢复和审计追踪
  - 系统化评测集、自动化回归和 Agent 质量评估
  - 生产监控、告警、链路追踪和灰度发布
  - 复杂报告编辑、协同工作流和权限化文件管理
  - 大模型微调与私有化模型训练

## 验收标准

- **R1**：用户通过 POST `/api/task` 提交 query 后，系统返回 `thread_id`，并在后台启动 DeepAgents 执行任务，最终生成可下载的研究报告。
- **R2**：前端连接 `/ws/{thread_id}` WebSocket 后，在任务执行期间能收到 `tool_start`、`assistant_call`、`task_result`、`error`、`task_cancelled` 等事件。
- **R3**：用户通过 POST `/api/upload` 上传文件后，文件保存到 `updated/session_{thread_id}` 目录，后续任务的 path_instruction 中包含已上传文件列表。
- **R4**：当任务需要互联网公开资料时，主智能体调度网络搜索助手，调用 `internet_search`（Tavily）返回搜索结果，并保留标题和来源链接。
- **R5**：当任务需要结构化数据时，主智能体调度数据库查询助手，先 `list_sql_tables` 发现表，再 `get_table_data` 预览数据，最后 `execute_sql_query`（只读）获取结果。
- **R6**：当任务需要私有知识库内容时，主智能体调度知识库研读助手，调用 `search_paper_library` / `retrieve_paper_evidence` 检索相关片段，返回结果含 `source_type: "knowledge_base"` 字段。
- **R7**：主智能体调用 `generate_markdown` 工具在工作目录生成 Markdown 文件，前端可通过 `/api/files` 和 `/api/download` 查看和下载。
- **R8**：主智能体先调用 `generate_markdown` 生成 Markdown，再调用 `convert_md_to_pdf` 在同目录生成 PDF 文件。
- **R9**：GET `/api/files?path=...` 返回指定目录下所有文件元数据，GET `/api/download?path=...` 返回文件流；路径安全校验阻止越权访问 output 目录之外的文件。
- **R10**：POST `/api/task/{thread_id}/cancel` 取消指定任务，前端 WebSocket 收到 `task_cancelled` 事件。
- **R11**：同一 `thread_id` 的多轮请求通过 LangGraph `InMemorySaver` checkpoint 保持上下文，后续轮次可引用前一轮结果。
- **R12**：任务完成后，前 500 字结果保存到 `memory_store.json`；新任务启动时，query 关键词子串匹配历史记忆（重叠率 ≥ 0.5），匹配结果注入 system prompt。
- **R13**：`execute_sql_query` 仅放行以 `SELECT` / `SHOW` / `WITH` / `DESCRIBE` / `EXPLAIN` 开头的 SQL；非只读查询在工具层直接返回拒绝消息。
- **R14**：`app/config/retrieval_config.py` 中可配置 `rrf_k`、`enable_reranker`、`rerank_model`、`candidate_multiplier`、`final_top_k`、`bm25_tokenizer` 等参数。

## 依赖与约束

- **关键依赖**：
  - Python ≥ 3.12，< 3.13
  - DeepAgents == 0.5.7
  - LangGraph == 1.1.10
  - FastAPI + Uvicorn（后端服务）
  - Tavily API Key（互联网搜索）
  - MySQL 8.4 + mysql-connector-python（结构化数据）
  - RAGFlow API / LlamaIndex（私有知识库）
  - React + Vite + Ant Design + Tailwind CSS（前端）
  - Docker + Docker Compose（容器化部署）
- **运行时约束**：
  - OpenAI 兼容的 LLM 接口（base_url + api_key + model_name）
  - 前端默认连接 `http://localhost:8000`，可通过 `VITE_API_BASE_URL` 配置
  - 会话文件存放路径：`output/session_{thread_id}/`，上传文件暂存：`updated/session_{thread_id}/`
- **性能约束**：
  - Query 最大长度 2000 字符
  - 网络搜索助手最多执行 5 次搜索
  - 向量检索候选集：`top_k * 3` 个片段，最终取 top_k = 5
- **合规约束**：
  - SQL 工具只允许只读查询，禁止写入和 DDL 操作
  - 文件下载限制在 output 目录范围内，阻止路径穿越

## 非目标

- 不追求成为企业级生产系统；本项目的首要角色是 DeepAgents 多智能体工程的学习范例
- 不支持多用户隔离、权限管理、审计追踪等企业治理能力
- 不涉及大模型微调和私有模型部署

## 附录

- **术语表**：
  | 术语 | 说明 |
  |------|------|
  | DeepAgents | 用于创建多智能体应用的开源框架，支持 Orchestrator-Workers 模式 |
  | 主智能体 | 负责任务拆解、助手调度、信息汇总和文件交付的核心智能体 |
  | 子智能体 | 专注于单一信息来源或能力的专用智能体（网络搜索 / 数据库查询 / 知识库研读） |
  | RRF | Reciprocal Rank Fusion，倒数排序融合算法 |
  | ContextVar | Python `contextvars` 模块，用于异步任务上下文隔离 |
  | InMemorySaver | LangGraph 内置的会话检查点存储器，基于 thread_id 隔离会话上下文 |

- **参考链接**：
  - 项目仓库：https://github.com/didilili/deepsearch-agents
  - 配套教程：https://didilili.github.io/ai-agents-from-zero/
  - DeepAgents 文档：https://deepagents.readthedocs.io

- **变更记录**：
  | 版本 | 日期 | 变更内容 | 作者 |
  |------|------|----------|------|
  | v1.0 | 2026-06-11 | 初稿 | [请补充] |
