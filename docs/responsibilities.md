Python，LangGraph，Qwen2.5-Coder，FastAPI，MySQL，Qdrant，Elasticsearch，React

面向企业内部知识检索与数据分析场景，基于 FastAPI 构建 RESTful API 层，设计 POST /api/query 统一问答入口接收自然语言请求，通过 LangGraph 双 Agent 路由分发至 RAG 问答链路或 NL2SQL 链路，支持流式 SSE 返回，P50 延迟 1.9s

RAG 链路调用 Qdrant API（/collections/{name}/points/search）执行向量检索，同时调用 Elasticsearch _search API 执行 BM25 全文检索，在应用层实现 RRF 融合排序；设计父子索引结构，子块命中后通过 parent_id 字段回溯父块，调用 Qdrant points API 按 ID 查询父块原文组装 LLM 上下文

NL2SQL 链路基于 LangGraph 多阶段编排：先调用 MySQL INFORMATION_SCHEMA 接口检索相关表和字段元数据，再调用 Qwen2.5-Coder API（chat/completions）生成 SQL，然后执行 EXPLAIN 校验语法和成本，最后通过 mysql-connector-python execute() 执行只读查询并返回结果集；执行报错时自动提取错误信息拼接至 prompt 重新调用 LLM 修正，形成生成-校验-修正-执行闭环

通过 FastAPI middleware 统一拦截请求并检测 Prompt Injection 模式，命中时直接拒绝并写入日志；每次 NL2SQL 查询记录 user_query、生成的 SQL、执行结果和溯源来源到 MySQL audit_log 表，支持后续审计和调试

构建 200 条测试用例集，覆盖常规问答、多轮对话、注入攻击和跨文档推理等场景，通过 pytest + httpx TestClient 自动化调用全部 API 断言响应状态和字段完整性，常规问答覆盖率达到 96%
