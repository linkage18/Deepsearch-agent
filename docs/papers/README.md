# 论文库目录

将需要进入 LlamaIndex 本地论文库的资料放在本目录下，例如：

- 论文 PDF
- 阅读笔记 Markdown
- 综述材料 TXT / Markdown
- 技术报告 DOCX

后端工具会读取 `LLAMAINDEX_PAPER_DIR` 指向的目录，默认就是 `docs/papers`。
首次检索时会自动建立索引，并持久化到 `LLAMAINDEX_INDEX_DIR`。
