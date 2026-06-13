"""
论文知识库子智能体配置模块

将 prompts.yml 中的 paper_knowledge 配置与 LlamaIndex 工具组装成
DeepAgents 可识别的字典式子智能体。主智能体会在需要检索论文正文、
方法细节、实验设置、结论和局限性时调用它。
"""

from app.agent.prompts import sub_agents_content
from app.tools.llamaindex_tools import (
    build_paper_card,
    list_paper_library_files,
    retrieve_paper_evidence,
    search_paper_library,
)


paper_knowledge_agent = {
    "name": sub_agents_content["paper_knowledge"]["name"],
    "description": sub_agents_content["paper_knowledge"]["description"],
    "system_prompt": sub_agents_content["paper_knowledge"]["system_prompt"],
    "tools": [
        list_paper_library_files,
        search_paper_library,
        retrieve_paper_evidence,
        build_paper_card,
    ],
}
