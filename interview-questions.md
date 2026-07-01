# DeepSearch Agents 项目面试 100 问

---

## 一、计算机基础（20 题）

### 操作系统与并发

1. **信号量与 asyncio 信号量**  
   本项目使用 `asyncio.Semaphore` 限制 Agent 并发数为 4。请解释信号量的工作原理，以及为什么用 `asyncio.Semaphore` 而非 `threading.Semaphore`？

2. **ContextVar 与会话隔离**  
   `ContextVar` 在本项目中用于会话隔离。请解释 Python `contextvars` 模块的设计目的，以及它为什么比 `threading.local` 更适合 async/await 场景？

3. **Background Task 生命周期**  
   `asyncio.create_task` 创建的 background task 在什么情况下会被垃圾回收？项目中 `active_tasks` 字典持有 task 引用的作用是什么？

4. **CancelledError 传播**  
   当用户取消任务时（`task.cancel()`），`asyncio.CancelledError` 如何在调用栈中传播？项目中在 `run_deep_agent` 的 `except asyncio.CancelledError` 里做了哪些清理工作？

5. **进程/线程/协程对比**  
   进程、线程、协程的区别是什么？本项目为什么选择 asyncio 协程模型而不是多线程？

### 网络与协议

6. **WebSocket vs HTTP 长轮询**  
   WebSocket 和 HTTP 长轮询有什么区别？本项目为什么选择 WebSocket 做实时事件推送？

7. **run_coroutine_threadsafe 场景**  
   项目中 `ConnectionManager` 需要把 WebSocket 消息投递回 FastAPI 的事件循环。请解释 `asyncio.run_coroutine_threadsafe` 的作用和使用场景。

8. **HTTP 状态码语义**  
   请解释 HTTP 状态码 400/404/500 的语义区别。项目 API 中哪些场景返回 400？

9. **Nginx 反向代理路由**  
   Nginx 反向代理在本项目中的作用是什么？`docker/nginx.conf` 中 `/api/*` 和 `/ws/*` 的路由规则为什么需要分别配置？

10. **CORS 跨域**  
    CORS（跨域资源共享）是什么？为什么开发环境下前端 `localhost:5173` 调用后端 `localhost:8000` 会触发 CORS 预检？

### 数据库

11. **SQLite WAL 模式**  
    SQLite WAL（Write-Ahead Logging）模式相比默认的 DELETE 模式有什么优势？本项目为什么选择 WAL？

12. **事务隔离级别与 BEGIN IMMEDIATE**  
    什么是事务隔离级别？SQLite 的 `BEGIN IMMEDIATE` 和普通的 `BEGIN` 有什么区别？本项目 `append_turn` 为什么要用 `BEGIN IMMEDIATE`？

13. **MySQL TRADITIONAL SQL Mode**  
    MySQL 的 `TRADITIONAL` SQL Mode 有什么作用？项目中为什么要设置 `--sql-mode=TRADITIONAL`？

14. **数据库连接池**  
    请解释数据库连接池的必要性。本项目中 MySQL 连接为什么没有使用连接池（如 SQLAlchemy）而是每次新建连接？

15. **索引最左前缀原则**  
    什么是索引的最左前缀原则？项目中 `run_events` 表的 `idx_run_events_thread_created` 索引如何加速查询？

### 数据结构与算法

16. **RRF 融合算法**  
    RRF（Reciprocal Rank Fusion）是本项目检索融合的核心算法。请推导其公式 `1/(k+rank)`，并解释常数 k 的作用。

17. **BM25 vs TF-IDF**  
    BM25 算法与 TF-IDF 的核心区别是什么？本项目为什么在向量检索的候选集上再跑 BM25，而不是直接在全库上跑？

18. **余弦相似度**  
    余弦相似度（Cosine Similarity）的计算公式是什么？本项目如何用它来判断 claim 与 evidence 的语义匹配程度？

19. **哈希摘要（SHA-256）**  
    哈希摘要（SHA-256）在本项目的 manifest 机制中起什么作用？为什么用文件大小 + 修改时间 + 内容的组合来生成 digest？

20. **chunk_size 与 chunk_overlap**  
    本项目分块策略使用 `chunk_size=512, chunk_overlap=64`。请解释 chunk_overlap 的作用，以及为什么不宜过大或过小？

---

## 二、八股题（25 题）

### Python / FastAPI

21. **async def vs def**  
    `async def` 和 `def` 定义的 FastAPI 端点有什么区别？什么情况下应该用 `async def`？

22. **lifespan 上下文管理器**  
    请解释 FastAPI 的 `lifespan` 上下文管理器的作用。本项目在 `lifespan` 中做了什么事？

23. **Pydantic 数据校验**  
    Pydantic `BaseModel` 的数据校验是如何工作的？本项目 `TaskRequest` 模型校验了哪些字段？

24. **with 语句与 contextmanager**  
    Python 的 `with` 语句和 `@contextmanager` 装饰器是如何配合使用的？请阅读项目中 `_connect()` 的实现并说明其设计意图。

25. **@tool 装饰器**  
    `@tool` 装饰器（来自 `langchain_core.tools`）是如何把一个普通函数包装成 LLM 可调用工具的？工具的 docstring 和类型注解分别起什么作用？

26. **__new__ vs __init__**  
    Python `__new__` 和 `__init__` 的区别是什么？本项目 `ToolMonitor` 为什么用 `__new__` 实现单例模式？

### LangGraph / DeepAgents

27. **InMemorySaver checkpoint 隔离**  
    LangGraph 的 `InMemorySaver` 是什么？它如何基于 `thread_id` 实现会话级别的 checkpoint 隔离？

28. **tools 与 subagents 参数**  
    `create_deep_agent` 的 `tools` 参数和 `subagents` 参数分别是什么？它们在架构层面的职责如何划分？

29. **astream chunk 结构**  
    LangGraph 中 `astream` 返回的 chunk 结构是什么样的？本项目中如何解析 `{"model": {"messages": [...]}}` 这样的状态片段？

30. **Orchestrator-Workers 模式**  
    什么是 Orchestrator-Workers 模式？本项目的一主三从架构如何体现这种模式？

31. **子智能体调用机制**  
    DeepAgents 调用子智能体时会产生名为 `task` 的 tool_call，请解释这个机制：主智能体如何知道该调用哪个子智能体？

32. **StateGraph 状态传递**  
    请解释 LangGraph 中的 StateGraph 概念。`messages` 状态键如何在节点间传递和累积？

### LlamaIndex / RAG

33. **VectorStoreIndex 构建流程**  
    LlamaIndex 的 `VectorStoreIndex` 是如何构建的？请简述从 `SimpleDirectoryReader` → `SentenceSplitter` → `VectorStoreIndex` 的完整流程。

34. **StorageContext 持久化**  
    LlamaIndex 的 `StorageContext.from_defaults(persist_dir=...)` 持久化了哪些内容？索引重建的判断依据是什么？

35. **Embedding 模式对比**  
    什么是 embedding？本项目支持哪三种 embedding 模式（mock/openai/local）？各自的适用场景是什么？

36. **SentenceSplitter vs TokenTextSplitter**  
    `SentenceSplitter` 和 `TokenTextSplitter` 的区别是什么？本项目为什么选择 `SentenceSplitter`？

### React / TypeScript / 前端

37. **useRef vs useState**  
    React 的 `useRef` 和 `useState` 有什么区别？本项目 `useDeepAgentSession` 中为什么用 `useRef` 持有 WebSocket 实例？

38. **useCallback 与闭包陷阱**  
    React `useCallback` 的依赖数组（deps）在什么情况下会导致闭包陷阱？本项目中 `clearSocketTimers` 为什么用 `useCallback` 包裹？

39. **Record<string, unknown> vs any**  
    请解释 TypeScript 中的 `Record<string, unknown>` 类型。本项目 `extractString` 函数为什么用 `unknown` 而非 `any`？

40. **Vite 优势与配置**  
    Vite 相比 webpack 有什么优势？本项目 `vite.config.ts` 中配置了哪些关键项？

41. **antd 主题定制**  
    Ant Design（antd）组件库的主题定制是如何实现的？本项目 Neo Kinpaku 配色方案通过哪些 CSS 变量实现？

### Docker / DevOps

42. **Docker build context 优化**  
    Docker 的 `build context` 是什么？本项目通过 `.dockerignore` 将构建上下文从 500MB 降到 37MB，列举至少 3 个被排除的目录。

43. **depends_on 与 healthcheck**  
    `docker-compose.yaml` 中 `depends_on` 和 `healthcheck` 是如何配合的？为什么 backend 容器要 `depends_on mysql (condition: service_healthy)`？

44. **Docker volume vs bind mount**  
    Docker volume 和 bind mount 的区别是什么？本项目使用了哪几种 volume？为什么模型缓存要用 volume 而非直接写在镜像里？

45. **多阶段构建 vs 单阶段**  
    什么是 Docker 的多阶段构建（multi-stage build）？本项目为什么选择了单阶段 Dockerfile？

---

## 三、场景题（20 题）

46. **完整调用链路分析**  
    用户提交了一个任务「对比 MIM-Reasoner 和 Graph Bayesian Optimization 的方法差异」，请描述从 POST `/api/task` 到最终生成 Markdown 报告的完整调用链路。

47. **断线恢复机制**  
    用户在任务执行过程中刷新了浏览器页面，导致 WebSocket 断开。本项目的断线恢复机制是如何工作的？（提示：`listTaskEvents` 接口 + `refreshEvents`）

48. **搜索引擎降级策略**  
    如果 SearXNG 搜索引擎不可用（容器挂了），Agent 执行会怎样？你会如何设计降级策略？

49. **大文件上传处理**  
    用户上传了一个 30MB 的 PDF 文件，系统会如何处理？请列举所有触发拒绝的条件。

50. **SQL 注入防护纵深**  
    假设用户输入 `"; DROP TABLE papers; --` 作为搜索 query，系统如何防止 SQL 注入？请逐层说明防护措施。

51. **重复提交处理**  
    同一个 `thread_id` 被连续提交了两次任务，系统会如何处理旧任务？这样设计的原因是什么？

52. **增量索引与 manifest 机制**  
    假设论文库中新增了一篇 PDF，Agent 在下一次检索时如何确保新论文被索引？manifest 机制的具体流程是什么？

53. **并行上传与检索冲突**  
    前端用户上传 PDF 到知识库（`POST /api/knowledge/upload`）后，索引何时重建？如果上传过程中另一个用户正在检索会发生什么？

54. **任务超时处理**  
    假设 Agent 任务执行超时（超过 300 秒），系统会如何处理？`AGENT_TASK_TIMEOUT_SECONDS` 在哪些地方生效？

55. **LLM 格式错误兜底**  
    如果 LLM API（如 Qwen）返回了格式错误的 tool_call（例如 JSON 不合法），DeepAgents 框架会如何处理？你可以设计什么兜底策略？

56. **子智能体调用顺序决策**  
    用户说「帮我调研影响力最大化算法的最新进展」，Agent 先后调用了网络搜索助手、知识库助手和数据库助手。主智能体如何决定调用顺序？prompt 中哪些约束起了关键作用？

57. **引用校验失败分析**  
    生成的综述报告中出现了「A 方法比 B 方法好 30%」的结论，但 citation_checker 标记为 `unfounded`（相似度 < 0.25）。请问可能的原因是什么？你会如何改进？

58. **ContextVar 并发隔离**  
    多个用户同时提交任务时，`ContextVar` 如何保证各自的任务写入各自的工作目录而不会"串台"？

59. **前后端输入校验**  
    前端 `ChatComposer` 组件中，用户输入一段包含换行和特殊字符的长 query。前后端各做了哪些输入校验和清洗？

60. **崩溃恢复与半成品保护**  
    Agent 在生成 Markdown 报告时，调用了 `generate_markdown` 工具。如果工具执行过程中 Python 进程崩溃，当前会话的产物（半成品 Markdown 文件）会丢失吗？如何改进？

61. **论文卡片生成流水线**  
    论文卡片（Paper Card）是如何生成的？从检索证据到结构化卡片的流水线是怎样的？

62. **引用校验同步 vs 异步**  
    引用校验模块是同步还是异步执行的？为什么这样设计？如果要在报告生成过程中实时校验，会引入什么问题？

63. **WebSocket 重连与状态恢复**  
    前端 WebSocket 连接在什么情况下会触发重连？重连后的状态恢复流程是怎样的？（提示：`useDeepAgentSession` 中的 `reconnectTimerRef` 和心跳机制）

64. **系统扩展瓶颈分析**  
    如果要将本项目从单机部署扩展到支持 1000 个并发用户，当前的哪些设计会成为瓶颈？请列举至少 3 个。

65. **搜索结果质量判定**  
    用户提交 query「搜索 ReAct 论文的相关资料」后，SearXNG 返回了 10 条结果但全是中文网页。Agent 如何判断这些结果的质量？prompt 中有哪些约束？

---

## 四、项目设计与工程化（25 题）

### 架构设计

66. **搜索后端切换决策**  
    本项目从原版的 Tavily 搜索切换到了 SearXNG 自托管搜索。请分析这个决策背后的工程考量（成本、可控性、隐私等），以及切换时对代码的影响范围。

67. **存储方案升级决策**  
    从 JSON 文件存储升级到 SQLite + WAL 的决策依据是什么？请对比两种方案在并发安全、查询能力、运维复杂度方面的优劣。

68. **三层数据隔离设计评价**  
    本项目采用了 `user_id + workspace_id + thread_id` 三层数据隔离（原版只有 thread_id）。当 user_id 和 workspace_id 尚未实现时，目录结构已经为此预留了扩展点。请评价这种"超前设计"的利弊。

69. **健康检查端点设计**  
    系统提供了 `/health/live` 和 `/health/ready` 两个健康检查端点。请解释 Kubernetes 中 liveness probe 和 readiness probe 的区别，以及本项目这两个端点分别适合哪种 probe。

### 检索系统设计

70. **四层检索流水线设计**  
    检索流水线为什么设计为四层（向量 → BM25 → RRF → MiniLM 重排序）而不是一步到位？每一层解决了什么问题？

71. **配置即代码设计**  
    `retrieval_config.py` 中将所有检索参数收敛到一个字典的设计意图是什么？这种"配置即代码"的方式和 YAML/JSON 配置文件方式各有什么优劣？

72. **评测框架可扩展性**  
    评测脚本 `evaluate.py` 支持三种检索策略的 A/B 对比。如果要加入第四种策略（如 ColBERT 端到端检索），需要在评测框架中添加多少代码？这个框架的可扩展性如何？

73. **模型缓存目录设计**  
    本项目 embedding 模型缓存收敛到 `data/model_cache` 目录。在 Docker 部署和本地开发两种场景下，这个设计分别解决了什么问题？

74. **BM25 候选集设计**  
    为什么 BM25 的候选集是在向量检索的结果上计算，而不是在全库上计算？这样做的 trade-off 是什么？

### 安全设计

75. **SQL 纵深防御评价**  
    SQL 防注入采用了"前缀白名单 + 多语句拦截 + 关键字黑名单 + 表名白名单"四层防护。请评价这种纵深防御设计的优劣，是否有绕过可能？

76. **路径穿越防护原理**  
    路径穿越防护中 `resolve() + is_relative_to()` 的组合为什么能防止 `../../etc/passwd` 这类攻击？这两个方法各自解决了什么问题？

77. **文件上传安全遗漏**  
    文件上传限制了三项：数量 ≤5、大小 ≤20MB、后缀白名单。是否还缺少其他必要的安全控制？如果用户上传一个伪装成 `.pdf` 的病毒文件，系统会怎样？

78. **限流策略选择**  
    Agent 限流使用 `asyncio.Semaphore(4)`。当第 5 个请求到达时会发生什么？这种排队等待和直接返回 429 Too Many Requests 各有什么适用场景？

### 前端工程化

79. **大型自定义 Hook 测试**  
    前端 `useDeepAgentSession` 是一个近 300 行的自定义 Hook。它封装了哪些职责？如果要对这个 Hook 做单元测试，你会如何拆分？

80. **组件职责拆分**  
    前端组件树中 `App.tsx` 包含了侧边栏、主区域、WebSocket 状态管理等多重职责。在后续迭代中你会如何拆分这些关注点？

81. **主题切换改造**  
    前端 Neo Kinpaku 暖黑金配色方案通过 CSS 变量实现。如果要支持暗色/亮色主题切换，当前方案需要做哪些改造？

### 监控与可观测性

82. **ToolMonitor 多路输出设计**  
    `ToolMonitor` 单例同时支持 WebSocket 推送、SQLite 持久化、控制台输出和文件日志四种输出渠道。请评价这种设计的优缺点。如果要添加 Prometheus metrics 输出，你会如何扩展？

83. **审计日志敏感信息取舍**  
    工具调用审计日志 `tool_calls.log` 只记录了时间戳、事件类型和工具名，"不记录参数值防敏感泄漏"。这个取舍合理吗？如果排查问题时确实需要参数值怎么办？

84. **静默降级策略边界**  
    项目中的错误处理大量使用了 `except Exception as exc: print(...)` 的模式，例如记忆检索失败时"跳过"。这种"静默降级"策略在什么场景下是合理的，什么场景下可能掩盖严重 bug？

### 测试与质量

85. **测试维度与 CI 补充**  
    `tests/test_citation_verification.py` 和 `tests/test_production_hardening.py` 分别覆盖了什么测试维度？如果要建立 CI/CD 流水线，还需要补充哪些类型的测试？

86. **评测数据管理**  
    评测数据集 `_ground_truth.json` 包含 20 条 query 和对应的正确答案。如果要将其扩展为 200 条并支持自动化回归，你会如何设计评测数据的管理和版本控制？

87. **测试文件规范化**  
    项目中的 `_benchmark.py` 和 `_test_speed.py` 文件位于项目根目录而非 `tests/` 目录。这种做法反映了什么工程习惯？你会如何规范化？

### 部署与运维

88. **Docker 网络容器名解析**  
    Docker Compose 编排了 4 个容器，backend 通过容器名 `mysql:3306` 连接数据库而非 `localhost`。请解释 Docker 网络中容器名解析的原理。

89. **共享 .env 文件风险**  
    项目中 `.env` 同时被 Docker Compose（`--env-file .env`）和 Python（`python-dotenv`）读取。这种共享 `.env` 文件的做法有什么风险？如何改进？

90. **零宕机部署改造**  
    如果要实现零宕机部署（zero-downtime deployment），当前的 Docker Compose 方案需要做哪些改造？

---

## 五、HR 题（10 题）

91. **项目 3 分钟介绍**  
    请用 3 分钟介绍这个项目。重点突出：解决了什么问题、你的角色、技术亮点和你最自豪的一个改进。

92. **最大技术挑战**  
    你在这个项目中遇到的最大技术挑战是什么？你是如何解决的？

93. **开源项目二次开发**  
    这个项目是基于开源项目二次开发的。你是如何选择基础项目的？在原版基础上你做了哪些属于你自己的贡献？

94. **团队协作与 Code Review**  
    团队协作中，你和团队成员（如果有）是如何分工的？代码审查（Code Review）的流程是怎样的？

95. **未来 3 个月规划**  
    如果给你更多时间（比如 3 个月），你会为这个项目添加什么功能？为什么？

96. **教学性与生产可用性的平衡**  
    项目中有一个 `examples/` 目录包含了 15 个 DeepAgents 学习示例。你写这些示例的目的是什么？如何平衡"教学性"和"生产可用性"？

97. **从错误中学习**  
    描述一次你在项目中犯了错误并从中学习的经历。（提示：可以从架构决策、bug 修复、方案选型等角度回答）

98. **文档的价值**  
    这个项目从 PRD 到架构文档到评测报告都有完整文档。你如何看待文档在软件工程中的作用？写文档的时间占总开发时间的比例是多少？

99. **个人发展规划**  
    你希望下一份工作/下一个项目在哪些方面有所提升？你个人技术发展的下一步规划是什么？

100. **理想团队与工作方式**  
    如果我们录用你，你期望在什么样的团队和项目中工作？什么样的工作方式最能激发你的产出？

---

> 以上 100 题覆盖：操作系统/网络/数据库基础（1-20）、Python/FastAPI/LangGraph/LlamaIndex/React/Docker 八股（21-45）、真实系统场景分析（46-65）、架构设计/安全/检索系统/前端/监控/测试/部署工程化（66-90）、行为面与职业发展（91-100）。建议根据面试岗位侧重点（后端/前端/全栈/算法）挑选 15-20 题深度追问。
