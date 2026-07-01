"""
主智能体组装与异步执行模块

负责把模型、主提示词、文件类工具和三个论文研读专家子智能体组装成 DeepAgent，
并提供 run_deep_agent 作为后续 API 层调用的统一入口。运行时还会为每个
session_id 创建独立工作目录，并把工具调用、子智能体调用和最终结果推送给前端。
"""

import asyncio
import re
import shutil

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.llm import model
from app.agent.prompts import main_agent_content
from app.agent.subagents.database_query_agent import database_query_agent
from app.agent.subagents.network_search_agent import network_search_agent
from app.agent.subagents.paper_knowledge_agent import paper_knowledge_agent
from app.api.context import (
    reset_session_context,
    set_session_context,
    set_thread_context,
)
from app.api.monitor import monitor
from app.config.paths import REPORT_DIR, UPLOAD_DIR, ensure_runtime_dirs
from app.utils.logging import get_logger

logger = get_logger(__name__)

from app.memory.memory_store import memory_store
from app.models.session import save_session, update_session
from app.tools.markdown_tools import generate_markdown
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.upload_file_read_tool import read_file_content

main_agent = create_deep_agent(
    model=model,
    system_prompt=main_agent_content["system_prompt"],
    tools=[generate_markdown, convert_md_to_pdf, read_file_content],
    checkpointer=InMemorySaver(),
    subagents=[database_query_agent, network_search_agent, paper_knowledge_agent],
)

ensure_runtime_dirs()
project_root_path = REPORT_DIR.parent


async def run_deep_agent(task_query, session_id):
    logger.info("开始执行会话", extra={"session_id": session_id, "query": task_query[:80]})

    try:
        save_session(session_id, task_query)
    except Exception as exc:
        logger.warning("保存会话元数据异常", extra={"session_id": session_id, "error": str(exc)})

    session_dir = REPORT_DIR / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    session_dir_str = str(session_dir).replace("\\", "/")
    try:
        relative_session_dir_str = str(session_dir.relative_to(project_root_path)).replace(
            "\\", "/"
        )
    except ValueError:
        relative_session_dir_str = session_dir_str

    updated_dir_path = UPLOAD_DIR / f"session_{session_id}"
    updated_info_prompt = ""
    if updated_dir_path.exists():
        files = [f.name for f in updated_dir_path.iterdir() if f.is_file()]
        if files:
            for filename in files:
                shutil.copy2(updated_dir_path / filename, session_dir / filename)
            updated_info_prompt = (
                "\n    [已上传文件] 已加载到工作目录:\n"
                + "\n".join([f"    - {f}" for f in files])
                + "\n    请优先使用工具（read_file_content）读取并参考这些文件。"
            )

    session_dir_token = set_session_context(session_dir_str)
    session_id_token = set_thread_context(session_id)

    monitor.report_session_dir(session_dir_str)

    config = {"configurable": {"thread_id": session_id}}

    path_instruction = f"""
    【工作环境指令】
    工作目录: {relative_session_dir_str}
    {updated_info_prompt}

    规则：
    1. 新生成文件必须保存到工作目录：'{relative_session_dir_str}/filename'
    2. 读取已上传的文件时，请直接将文件名作为 filename 参数传入 read_file_content
    3. 使用相对路径，禁止使用绝对路径
    4. 若存在上传文件，请先分析内容
    """

    memory_hint = ""
    try:
        search_keywords = re.split(r'[,，?\s]+', task_query.strip())
        seen = set()
        for kw in search_keywords:
            if len(kw) < 2 or kw in seen:
                continue
            seen.add(kw)
            matches = memory_store.search(kw)
            for m in matches:
                key_preview = m["key"][:60]
                content_preview = " ".join(m["content"].split())[:200]
                memory_hint += (
                    f"\n    - [{key_preview}]: {content_preview}"
                )
        if memory_hint:
            memory_hint = (
                "\n    【历史记忆参考】以下内容来自之前的会话，可参考："
                + memory_hint
            )
    except Exception as exc:
        logger.warning("记忆检索异常", extra={"session_id": session_id, "error": str(exc)})

    path_instruction += memory_hint

    final_result = ""

    try:
        async for chunk in main_agent.astream(
            {"messages": [{"role": "user", "content": task_query + path_instruction}]},
            config=config,
        ):
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue
                messages = state["messages"]
                if messages and isinstance(messages, list):
                    last_msg = messages[-1]
                    if node_name == "model":
                        if last_msg.tool_calls:
                            for tool_call in last_msg.tool_calls:
                                if tool_call["name"] == "task":
                                    monitor.report_assistant(
                                        tool_call["args"]["subagent_type"],
                                        {
                                            "description": tool_call["args"][
                                                "description"
                                            ]
                                        },
                                    )
                        elif last_msg.content:
                            logger.info("主智能体产生结果", extra={
                                "session_id": session_id,
                                "preview": last_msg.content[:100],
                            })
                            monitor.report_task_result(last_msg.content)
                            final_result = last_msg.content

    except asyncio.CancelledError:
        logger.info("任务被取消", extra={"session_id": session_id})
        monitor.report_task_cancelled()
        raise
    except Exception as e:
        logger.error("主智能体执行异常", extra={"session_id": session_id, "error": str(e)})
        monitor._emit("error", f"执行主智能体发生异常: {str(e)}")
    finally:
        reset_session_context(session_dir_token, session_id_token)

    if final_result:
        try:
            content_trimmed = " ".join(final_result.split())[:500]
            h1_match = re.search(r'^#\s+(.+)$', final_result, re.MULTILINE)
            if h1_match:
                memory_key = h1_match.group(1).strip()[:80]
            elif len(task_query) > 10:
                memory_key = task_query.strip()[:80]
            else:
                memory_key = content_trimmed[:80]
            memory_store.save(memory_key, content_trimmed, session_id)
            logger.debug("已保存长期记忆", extra={"key": memory_key})
        except Exception as exc:
            logger.warning("记忆保存异常", extra={"session_id": session_id, "error": str(exc)})

    if final_result:
        try:
            from app.models.session import append_turn
            append_turn(session_id, task_query, final_result[:2000])
            logger.debug("已保存对话记录", extra={"session_id": session_id})
        except Exception as exc:
            logger.warning("对话记录保存异常", extra={"session_id": session_id, "error": str(exc)})

    try:
        session_dir_path = REPORT_DIR / f"session_{session_id}"
        file_count = 0
        if session_dir_path.exists():
            file_count = len([f for f in session_dir_path.iterdir()
                              if f.is_file() and f.suffix.lower() in (".md", ".pdf", ".txt")])
        update_session(session_id, completed=True, file_count=file_count)
        logger.info("会话结束", extra={"session_id": session_id, "files": file_count})
    except Exception as exc:
        logger.warning("会话元数据更新异常", extra={"session_id": session_id, "error": str(exc)})


if __name__ == "__main__":
    import asyncio
    asyncio.run(
        run_deep_agent("从网络查询机器人信息，并生成Markdown文件", "test_session_001")
    )
