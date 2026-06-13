"""
会话元数据存储模块

职责单一：读写 output/sessions/index.json 中的会话元数据。
不负责事件持久化、不负责文件管理。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


SESSION_INDEX_PATH = Path("output") / "sessions" / "index.json"


def _load_index() -> dict[str, Any]:
    """加载完整索引，兜底空文件/损坏"""
    if not SESSION_INDEX_PATH.exists():
        return {"sessions": []}
    try:
        data = json.loads(SESSION_INDEX_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "sessions" in data:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"sessions": []}


def _save_index(index: dict[str, Any]) -> None:
    """写回索引"""
    SESSION_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_session(session_id: str, query: str) -> None:
    """
    创建新会话记录。自动从 query 截取 title。
    
    Args:
        session_id: 会话 ID（同时也是 thread_id）
        query: 用户首次提交的 query
    """
    index = _load_index()
    now = datetime.now(timezone.utc).isoformat()
    # 从 query 截取前 30 字作标题
    title = query.strip()[:30]
    if len(query) > 30:
        title += "..."

    # 如果已存在则跳过（幂等）
    for s in index["sessions"]:
        if s["id"] == session_id:
            return

    index["sessions"].append({
        "id": session_id,
        "title": title,
        "query_preview": query[:100],
        "created_at": now,
        "updated_at": now,
        "file_count": 0,
        "completed": False,
        "turns": [],
    })
    _save_index(index)


def append_turn(session_id: str, query: str, result: str) -> None:
    """
    追加一轮对话记录。
    turns 最多保留 20 条，超出时截断最旧的。
    
    Args:
        session_id: 会话 ID
        query: 用户 query
        result: Agent 最终回答（前 2000 字）
    """
    index = _load_index()
    for s in index["sessions"]:
        if s["id"] == session_id:
            turns = s.get("turns", [])
            turns.append({
                "query": query[:200],
                "result": result[:2000],
            })
            # 最多保留 20 条
            if len(turns) > 20:
                turns = turns[-20:]
            s["turns"] = turns
            s["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_index(index)
            return


def update_session(session_id: str, **kwargs: Any) -> None:
    """
    更新会话记录。可更新的字段：file_count, completed, title。
    
    Args:
        session_id: 会话 ID
        **kwargs: 要更新的字段
    """
    index = _load_index()
    now = datetime.now(timezone.utc).isoformat()
    for s in index["sessions"]:
        if s["id"] == session_id:
            for key, value in kwargs.items():
                if key in ("file_count", "completed", "title", "query_preview", "turns"):
                    s[key] = value
            s["updated_at"] = now
            _save_index(index)
            return
    # 不存在则静默忽略（兜底）
    print(f"[SessionStore] 尝试更新不存在的会话: {session_id}")


def list_sessions() -> list[dict[str, Any]]:
    """按更新时间降序返回所有会话"""
    index = _load_index()
    sessions = index.get("sessions", [])
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    """返回单条会话记录"""
    for s in list_sessions():
        if s["id"] == session_id:
            return s
    return None


def delete_session(session_id: str) -> bool:
    """删除会话记录"""
    index = _load_index()
    before = len(index["sessions"])
    index["sessions"] = [s for s in index["sessions"] if s["id"] != session_id]
    if len(index["sessions"]) < before:
        _save_index(index)
        return True
    return False
