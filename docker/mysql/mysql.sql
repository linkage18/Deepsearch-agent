-- 论文研读助手元数据数据库
-- 包含：论文、作者、主题、论文-作者关系、论文-主题关系、引用关系
-- 用于论文元数据查询子智能体演示按年份、作者、主题、会议和引用关系筛选论文。

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS deepsearch_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;
USE deepsearch_db;

DROP TABLE IF EXISTS citations;
DROP TABLE IF EXISTS paper_topics;
DROP TABLE IF EXISTS paper_authors;
DROP TABLE IF EXISTS topics;
DROP TABLE IF EXISTS authors;
DROP TABLE IF EXISTS papers;

CREATE TABLE papers (
    paper_id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    abstract TEXT,
    year INT NOT NULL,
    venue VARCHAR(100),
    paper_url VARCHAR(500),
    code_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE authors (
    author_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    affiliation VARCHAR(255)
);

CREATE TABLE paper_authors (
    paper_id INT NOT NULL,
    author_id INT NOT NULL,
    author_order INT NOT NULL,
    PRIMARY KEY (paper_id, author_id),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES authors(author_id) ON DELETE CASCADE
);

CREATE TABLE topics (
    topic_id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE paper_topics (
    paper_id INT NOT NULL,
    topic_id INT NOT NULL,
    PRIMARY KEY (paper_id, topic_id),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id) ON DELETE CASCADE
);

CREATE TABLE citations (
    paper_id INT NOT NULL,
    cited_paper_id INT NOT NULL,
    PRIMARY KEY (paper_id, cited_paper_id),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE,
    FOREIGN KEY (cited_paper_id) REFERENCES papers(paper_id) ON DELETE CASCADE
);

CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_venue ON papers(venue);
CREATE INDEX idx_authors_name ON authors(name);
CREATE INDEX idx_topics_name ON topics(name);

INSERT INTO papers (title, abstract, year, venue, paper_url, code_url) VALUES
('ReAct: Synergizing Reasoning and Acting in Language Models',
 '提出让语言模型交替生成推理轨迹和动作，以提升问答、事实核验和交互式任务中的可解释决策能力。',
 2023, 'ICLR', 'https://arxiv.org/abs/2210.03629', 'https://github.com/ysymyth/ReAct'),
('Reflexion: Language Agents with Verbal Reinforcement Learning',
 '提出通过语言反馈记忆帮助 Agent 反思失败经验，并在后续任务中利用自我反思改进表现。',
 2023, 'NeurIPS Workshop', 'https://arxiv.org/abs/2303.11366', 'https://github.com/noahshinn024/reflexion'),
('Toolformer: Language Models Can Teach Themselves to Use Tools',
 '研究语言模型如何通过自监督方式学习调用外部工具，包括计算器、检索系统和翻译工具。',
 2023, 'NeurIPS', 'https://arxiv.org/abs/2302.04761', ''),
('Generative Agents: Interactive Simulacra of Human Behavior',
 '构建带有记忆、反思和规划机制的生成式智能体，用于模拟可信的人类行为。',
 2023, 'UIST', 'https://arxiv.org/abs/2304.03442', ''),
('Voyager: An Open-Ended Embodied Agent with Large Language Models',
 '提出面向 Minecraft 的开放式终身学习 Agent，结合自动课程、技能库和迭代提示优化。',
 2023, 'arXiv', 'https://arxiv.org/abs/2305.16291', 'https://github.com/MineDojo/Voyager'),
('AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation',
 '提出通过多智能体对话构建复杂 LLM 应用的框架，支持可配置角色、工具使用和人机协作。',
 2023, 'arXiv', 'https://arxiv.org/abs/2308.08155', 'https://github.com/microsoft/autogen'),
('LangGraph: Building Stateful Multi-Agent Applications with LLMs',
 '介绍基于图的有状态 Agent 编排方式，适合构建可恢复、可观测、可控制的多步骤智能体应用。',
 2024, 'Technical Report', 'https://langchain-ai.github.io/langgraph/', 'https://github.com/langchain-ai/langgraph'),
('MemGPT: Towards LLMs as Operating Systems',
 '提出分层内存管理思想，让 LLM Agent 通过显式内存读写扩展长期上下文能力。',
 2024, 'arXiv', 'https://arxiv.org/abs/2310.08560', 'https://github.com/cpacker/MemGPT'),
('Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection',
 '提出让模型按需检索、生成并自我批判的框架，以提高长文本知识密集任务中的可靠性。',
 2024, 'ICLR', 'https://arxiv.org/abs/2310.11511', ''),
('GraphRAG: From Local to Global Graph-Based Retrieval-Augmented Generation',
 '研究使用知识图谱和社区摘要增强全局性问题回答，适合跨文档、多实体关系分析场景。',
 2024, 'Technical Report', 'https://arxiv.org/abs/2404.16130', 'https://github.com/microsoft/graphrag');

INSERT INTO authors (name, affiliation) VALUES
('Shunyu Yao', 'Princeton University'),
('Noah Shinn', 'Northeastern University'),
('Timo Schick', 'Meta AI'),
('Joon Sung Park', 'Stanford University'),
('Guanzhi Wang', 'NVIDIA'),
('Qingyun Wu', 'Microsoft Research'),
('LangChain Team', 'LangChain'),
('Charles Packer', 'UC Berkeley'),
('Akari Asai', 'University of Washington'),
('Microsoft Research', 'Microsoft');

INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES
(1, 1, 1),
(2, 2, 1),
(3, 3, 1),
(4, 4, 1),
(5, 5, 1),
(6, 6, 1),
(7, 7, 1),
(8, 8, 1),
(9, 9, 1),
(10, 10, 1);

INSERT INTO topics (name, description) VALUES
('Tool Use', '语言模型调用搜索、计算器、代码执行等外部工具的研究方向'),
('Reflection', 'Agent 通过自我反思、语言反馈或批判机制改进行为'),
('Long-Term Memory', 'Agent 记忆、技能库、长期上下文和外部存储机制'),
('Multi-Agent', '多个 Agent 之间的协作、对话和任务分解'),
('RAG', '检索增强生成、证据召回和基于文档的回答生成'),
('Planning', '任务规划、行动选择、开放式探索和多步骤推理');

INSERT INTO paper_topics (paper_id, topic_id) VALUES
(1, 1), (1, 6),
(2, 2), (2, 3),
(3, 1),
(4, 2), (4, 3), (4, 6),
(5, 3), (5, 6),
(6, 4), (6, 1),
(7, 4), (7, 6),
(8, 3),
(9, 5), (9, 2),
(10, 5), (10, 4);

INSERT INTO citations (paper_id, cited_paper_id) VALUES
(2, 1),
(4, 1),
(5, 1),
(5, 2),
(6, 1),
(6, 3),
(7, 6),
(8, 4),
(9, 1),
(10, 9);
