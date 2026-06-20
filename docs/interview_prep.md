# 深度研搜 · 多智能体论文系统 — 简历项目与面试准备

---

## 一、简历项目描述

### 精简版（200 字）

> **多源论文研读与综述生成智能体** — 独立开发
> 技术栈：Python、DeepAgents、LangGraph、LangChain、LlamaIndex、rank-bm25、sentence-transformers、OpenAI兼容接口（Qwen）、FastAPI、WebSocket、asyncio、Pydantic、MySQL、SearXNG、SQLite、pypdf、python-docx、pandas、ReportLab、Docker
>
> 面向科研文献调研场景，基于 DeepAgents + LangGraph 构建"一主三从"多智能体架构，支持主题输入、多源检索、证据聚合与 Markdown/PDF 综述导出。主智能体负责任务规划和综述生成，三个子智能体分别处理 SearXNG 网络搜索、MySQL 元数据查询和 LlamaIndex 论文库检索。检索采用向量 + BM25 + RRF 融合 + MiniLM 重排序的四层流水线。后端基于 FastAPI + WebSocket 实现异步任务和实时进度推送，通过 ContextVar 和会话目录隔离并发任务。工程化方面：SQLite + WAL 事务持久化会话/事件/证据/引用校验数据，SQL 只读白名单 + 多语句拦截防注入，路径穿越防护，Agent 限流和超时控制，健康检查接口，20 条 query 检索评测。设计结构化证据链和引用校验模块，Agent 生成结论强制绑定证据来源，MiniLM 自动校验引用真实性并输出量化指标。

---

### 详细版（面试 3 分钟介绍）

**项目名称**：多源论文研读与综述生成智能体

**技术栈**：Python、DeepAgents、LangGraph、LangChain、LlamaIndex、rank-bm25、sentence-transformers、OpenAI 兼容接口（Qwen）、FastAPI、WebSocket、asyncio、MySQL、SearXNG、SQLite、Docker

**项目背景**：面向科研文献调研场景，用户需要跨多来源检索论文资料（互联网、数据库、本地论文库），并汇总生成结构化综述报告。单一大模型无法完成跨源多步骤的深度调研。

**核心工作**：

1. **多智能体编排**：基于 DeepAgents 与 LangGraph 构建 Orchestrator-Workers 架构，主智能体通过 LangGraph StateGraph 运行时负责任务规划和多步推理，三个子智能体以字典式注册挂载为主图节点。子智能体调用通过 LangGraph 的 interrupt 机制实现：主图挂起 → 子图独立执行（自带 system_prompt + tools）→ 结果以 ToolMessage 回传 → 主图恢复。

2. **混合检索流水线**：基于 LlamaIndex 构建论文本地索引。检索流程：向量召回取 top_k×2 候选 → rank-bm25 在同一候选集上计算 BM25 分数 → RRF 融合（k=30）→ BM25 完全不可用时降级纯向量 → 可选用 MiniLM 重排序。返回结构化 evidence（含来源文件、页码、相似度分数、原文片段和元数据）。

3. **结构化证据链**：检索结果不是纯文本拼接，而是标准化的 evidence 数组（evidence_id / source_type / source / page / score / quote / metadata）。证据持久化到 SQLite 的 evidence_records 表，支持历史回溯。

4. **引用自动校验**：Agent 生成报告后，系统自动提取 `【证据: xxx】` / `【来源: 标题, p.5】` 标记，到 evidence_records 表查对应证据，用 MiniLM 计算 claim 与原文的语义相似度。≥ 0.5 标记 verified，0.25-0.5 标记 low_confidence，< 0.25 标记 unfounded。最终输出覆盖率、unfounded 率等量化指标。

5. **异步工程化**：FastAPI + WebSocket 实现异步任务调度。POST /api/task 经 asyncio.create_task 启动后台 Agent 执行，立即返回 thread_id。monitor 模块将工具调用 / 子智能体调用 / 任务结果封装为标准 WebSocket 事件。跨线程场景通过 asyncio.run_coroutine_threadsafe 保证线程安全。ContextVar 隔离 session_dir 和 thread_id，深层工具调用 get_session_context() 获取会话目录，无需逐层传参。

6. **安全与可靠性**：SQL 层校验只读白名单 + 多语句拦截 + 表名白名单；文件接口通过 resolve() + is_relative_to() 防路径穿越；Agent 信号量限流（默认 4 并发）+ 超时控制（300s）；SQLite WAL 模式事务写入会话/事件/记忆；健康检查接口；上传限制（5 文件 / 20MB / 后缀白名单）；所有运行时数据收敛到统一 DATA_ROOT 目录。

7. **评测体系**：20 条 ground truth query 的 Recall@K 和 MRR 评测脚本，支持 Markdown 表格输出，对比纯向量/混合/全链路三种检索策略。

---

## 二、按主题拆解面试回答

### 2.1 整体架构

**问：这个项目整体架构是什么样的？**

答：分四层：
- **用户交互层**：React 前端提交任务 + 实时展示 WebSocket 事件
- **API 服务层**：FastAPI 接收请求 → asyncio.create_task 丢到后台 → 立即返回 thread_id
- **Agent 执行层**：run_deep_agent() 创建会话目录、写入 ContextVar、调用 main_agent.astream() 驱动 LangGraph 图执行
- **图执行层**：LLM Node（推理决策）↔ Tool Node（工具/子智能体）循环，直到无 tool_calls 结束

### 2.2 DeepAgents + LangGraph

**问：DeepAgents 和 LangGraph 是什么关系？**

答：DeepAgents 是封装了 Orchestrator-Workers 模式的高级框架，底层基于 LangGraph 的 StateGraph。LangGraph 提供：StateGraph 有向图执行、InMemorySaver checkpoint 持久化、interrupt 子图挂起/恢复、astream 流式输出。DeepAgents 在此基础上封装了：create_deep_agent 一行注册主智能体 + 工具 + 子智能体、tool_call name="task" 自动路由到子智能体、子智能体字典式定义。如果用纯 LangGraph 手写需要约 60 行样板代码，DeepAgents 一行解决。

**问：子智能体怎么被调度的？**

答：主智能体 LLM 输出 tool_call，其中 name="task" 的被 DeepAgents 拦截。根据 subagent_type 找到注册的字典式子智能体，通过 LangGraph 的 interrupt 挂起主图、存储 checkpoint、创建子智能体的独立 subgraph 执行。子图完成后，结果包装成 ToolMessage 回到主图，主 LLM 继续推理。子智能体有自己的 system_prompt 和 tools，不会污染主智能体的上下文。

### 2.3 混合检索

**问：检索流水线具体怎么做的？**

答：四步。第一步，LlamaIndex 向量检索取 top_k × 2 个候选（默认 top_k=5 → candidate_k=10）。第二步，用 rank-bm25 在 10 个候选上算 BM25 分数。第三步，RRF 融合：score = 1/(k + vector_rank) + 1/(k + bm25_rank)，k=30。如果 BM25 最高分 < 0.1，说明词法完全失效，降级到纯向量。第四步，可选用 MiniLM 计算 query 和每个候选的余弦相似度做语义重排序。

**问：为什么用 RRF 而不是加权平均？**

答：RRF 只用排序位置，不依赖分数归一化。向量检索和 BM25 的分数尺度可能差几个数量级，加权平均需要调权重。RRF 对尺度不敏感，更鲁棒。

**问：Embedding 用的什么模型？**

答：通过 .env 的 LLAMAINDEX_EMBED_MODEL 配置。可选 mock（随机向量调试用）、openai（text-embedding-3-small）、local（all-MiniLM-L6-v2）。生产推荐 local 或 openai。

### 2.4 结构化证据链

**问：证据链结构化的好处是什么？**

答：第一，前端可以按来源/页码/分数/原文逐条展示，面试演示直观。第二，证据持久化到 SQLite，后续综述生成、引用校验、历史回溯都能复用。第三，每个 evidence 带 metadata（file_path、file_name、page_label），Agent 在生成结论时可以精确绑定到来源。

### 2.5 引用校验

**问：怎么保证 Agent 的引用是真实的？**

答：两个层面。第一，prompt 约束——要求 Agent 用 `【证据: evidence_id】` 或 `【来源: 标题, p.页码】` 格式引用，无来源的内容标注"待核验"。第二，后置自动校验——报告生成后，citation_checker 模块提取所有引用标记，到 evidence_records 表匹配证据，用 MiniLM 计算 claim 上下文和证据原文的语义相似度。≥ 0.5 verified，0.25-0.5 low_confidence，< 0.25 unfounded。最终输出覆盖率（verified + low_confidence 占比）和 unfounded 率。

**问：如果 MiniLM 模型不可用怎么办？**

答：有兜底——如果模型加载失败，直接按 evidence_id 匹配判 verified，因为精确 ID 匹配本身已经是强证据。

### 2.6 工程化

**问：并发请求怎么隔离？**

答：两个层次。第一，asyncio 层面——每个请求独立 create_task，任务之间天然隔离。第二，数据层面——ContextVar 存储 session_dir 和 thread_id，每个任务开始时 set、结束时 reset。工具函数直接调 get_session_context() 获取当前会话目录，无需传参，不会串到其他请求。

**问：安全性怎么做的？**

答：SQL：execute_sql_query 检查前缀（SELECT/SHOW/WITH/DESCRIBE/EXPLAIN），拒绝多语句（分号分隔），表名白名单 + 反引号转义。路径：resolve() 消除 ../ 后再 is_relative_to(output_dir) 检查。输入：query 最长 2000 字符。上传：最多 5 个文件、单文件 20MB、后缀白名单。Agent：信号量限流 4 并发 + 300s 超时。

**问：为什么用 SQLite 而不是 PostgreSQL？**

答：单机部署场景，SQLite + WAL 模式 + 事务隔离足够。不需要独立数据库服务，部署简单，适合实习项目。压测验证 100 路并发写入不丢数据。

### 2.7 评测

**问：检索效果怎么样？**

答：20 条 query 覆盖 10 篇论文。全链路（向量 + BM25 + RRF + 重排序）比纯向量 MRR 从 0.15 提升到 0.4167。评测脚本支持 --format md 输出 Markdown 表格，可以直接贴进面试文档。

---

## 三、面试官可能追问的细节

### DeepAgents / LangGraph

| 问题 | 答案 |
|------|------|
| create_deep_agent 内部做了什么？ | 创建 LangGraph StateGraph，注册 model_node、tool_node，配置 subagent 路由逻辑，绑定 checkpointer |
| interrupt 和 checkpoint 的关系？ | interrupt 挂起图执行，checkpoint 保存当前 state。恢复时 checkpointer.get() 读取 state，从挂起点继续 |
| 子智能体嵌套深度怎么控制？ | DeepAgents 的 SubAgentLimits 默认 5 层。本项目 1 主 3 从只有 2 层 |
| astream 的 chunk 结构？ | `{"node_name": {"messages": [AIMessage/ToolMessage]}}`。判断 node_name=="model" 且 last_msg.tool_calls 有内容表示 LLM 在调工具 |
| InMemorySaver 重启丢了怎么办？ | 当前设计如此。生产可换 SqliteSaver 或 PostgresSaver，接口完全兼容 |

### LlamaIndex 检索

| 问题 | 答案 |
|------|------|
| 索引重建策略？ | manifest 记录文件路径/大小/修改时间的哈希，变更时全量重建。论文库 ≤10 个文件，全量重建成本可接受 |
| chunk 策略？ | SentenceSplitter(chunk_size=512, chunk_overlap=64)。512 平衡语义完整性和检索精度 |
| BM25 tokenizer 中英文怎么处理？ | config.bm25_tokenizer: None 用 split()（空格分词），"jieba" 用 jieba.cut。英文论文 split > jieba |

### FastAPI / WebSocket

| 问题 | 答案 |
|------|------|
| 跨线程投递 WebSocket 事件？ | _emit 检测当前是否在主事件循环线程：同线程 create_task，不同线程 run_coroutine_threadsafe |
| 任务取消怎么实现的？ | task.cancel() 注入 CancelledError，await asyncio.wait_for(task, timeout=1.0) 等待响应 |
| 前端断线后事件怎么恢复？ | monitor 事件同时写入 SQLite run_events 表，前端重连后调 GET /api/task/{id}/events 拉取历史 |

### 检索评测

| 问题 | 答案 |
|------|------|
| 评测指标为什么选 Recall@K 和 MRR？ | Recall@K 衡量是否召回到正确文档，MRR 衡量最相关文档的排序位置——对 RAG 任务关键 |
| ground truth 来源？ | 手动标注的 20 条 query，每条对应 docs/papers/ 中的目标文档 ID |
| 混合检索相比纯向量提升多少？ | 以 MRR 计：纯向量 0.15、混合 0.3917、全链路 0.4167。混合阶段提升最显著（+160%） |

---

## 四、面试话术模板

### 项目亮点（30 秒）

> 我用 DeepAgents + LangGraph 构建了一个一主三从的论文研究智能体系统。主智能体负责任务规划，三个助手分别处理网络搜索、数据库查询和论文库检索。检索不只用向量，而是向量 + BM25 + RRF + 重排序四层流水线。最关键的是我设计了结构化证据链和引用校验——Agent 生成的每个结论必须绑定来源，系统会自动校验引用真实性，输出覆盖率等量化指标。工程上做了 SQL 防护、路径安全、限流超时、全量持久化。

### 遇到的最大挑战（1 分钟）

> 最大的挑战是引用可信度。最初只是 prompt 约束让 Agent 写来源，但面试时被追问"你怎么保证 Agent 没编造引用？"——靠 prompt 确实不够。后来我设计了 citation_checker 模块，Agent 生成报告后自动提取所有引用标记，去 evidence_records 表匹配证据，用 MiniLM 做语义相似度校验，输出 verified / low_confidence / unfounded 的量化统计。这样引用可信度从"prompt 承诺"变成了"系统验证"。

### 为什么用这个技术不用那个

> 为什么不用 PostgreSQL 用 SQLite？单机部署场景，SQLite + WAL + 事务隔离在 100 路并发下不丢数据，不需要独立数据库服务，部署简单。
>
> 为什么用 SearXNG 不用 Tavily？SearXNG 自托管零费用，聚合 70+ 引擎（含 arXiv、GitHub），适合教学和离线部署。Tavily 是付费 API 有额度限制。
>
> 为什么用 RRF 不用加权平均？RRF 只用排序位置不依赖分数归一化，向量分数和 BM25 分数尺度差异大时加权平均需要调权重，RRF 更鲁棒。

---

## 五、自学路线

| 阶段 | 学习内容 | 对应项目模块 |
|------|---------|-------------|
| 1 | Python 异步编程（asyncio、await、create_task） | FastAPI 后台任务 |
| 2 | FastAPI 基础（路由、Pydantic、WebSocket） | API 服务层 |
| 3 | LangChain 基础（ChatModel、Tool、tool decorator） | 工具定义 |
| 4 | LangGraph 核心（StateGraph、Node、Edge、Checkpoint） | Agent 图执行 |
| 5 | DeepAgents 框架（create_deep_agent、subagents） | 一主三从 |
| 6 | LlamaIndex（VectorStoreIndex、retriever、SentenceSplitter） | 论文库检索 |
| 7 | rank-bm25 + RRF 融合算法 | 混合检索 |
| 8 | sentence-transformers + MiniLM 重排序 | Rerank + 引用校验 |
| 9 | SQLite 事务 + WAL 模式 | 持久化层 |
| 10 | ContextVar + 并发隔离 | 工程安全 |
| 11 | Docker Compose 编排 | 容器化部署 |
| 12 | 检索评测方法论（Recall@K、MRR） | evaluation |
