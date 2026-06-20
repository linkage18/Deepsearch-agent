多源论文研读与综述生成智能体 — 独立开发  2025-11 ~ 2026-05

技术栈：Python、DeepAgents、LangGraph、LangChain、LlamaIndex、rank-bm25、sentence-transformers、OpenAI兼容接口（Qwen）、FastAPI、WebSocket、asyncio、Pydantic、MySQL、SearXNG、pypdf、python-docx、pandas、ReportLab、Docker、Docker Compose

项目背景：面向科研文献调研场景，构建多智能体论文助手，支持主题输入、论文上传、资料检索、证据聚合与 Markdown/PDF 综述导出

基于 DeepAgents 与 LangGraph 构建"一主三从"架构，主 Agent 通过 LangGraph StateGraph 运行时负责任务规划与多步推理，子 Agent 以字典式注册挂载为主图节点，经 interrupt 机制路由分别处理论文库检索、SearXNG 网络搜索和 MySQL 元数据查询，上下文通过 InMemorySaver checkpoint 按 thread_id 隔离

基于 LlamaIndex 构建论文本地索引，检索采用向量召回（可切换 Mock / OpenAI / HuggingFace Embedding）取 top_k × 2 候选，经 rank-bm25 在同一候选集上计算 BM25 分数后做 RRF 融合（k=30），最终由 sentence-transformers all-MiniLM-L6-v2 计算余弦相似度做语义重排序，返回带来源文件、页码和相关性分数的证据片段，支持父子文档回溯组装上下文

基于 FastAPI + WebSocket 实现异步任务编排：POST /api/task 经 asyncio.create_task 启动后台 Agent 执行，Pydantic 校验请求体，thread_id 标识会话；monitor 模块将 tool_start / assistant_call / task_result 封装为标准事件格式推送至前端，跨线程场景通过 asyncio.run_coroutine_threadsafe 保证线程安全；ContextVar 隔离 session_dir 和 thread_id，工具在深层调用栈中通过 get_session_context() 获取当前会话目录无需逐层传参

基于 Docker Compose 编排 4 容器（MySQL + Backend + Frontend + SearXNG），持久化卷管理模型缓存、索引和会话产物；SQL 工具层校验只读白名单（SELECT / SHOW / WITH / DESCRIBE / EXPLAIN），文件接口通过 resolve() + is_relative_to() 防路径穿越；多格式文件读取支持 pypdf / python-docx / pandas，报告生成通过 ReportLab 以 A4 版式、STSong-Light 中文字体渲染 Markdown 为 PDF
