"""
长期记忆存储模块

以 JSON 文件形式保存跨会话的关键信息。每条记忆包含：
- key：主题关键词（自动取第一个 # 标题或前 20 字）
- content：记忆内容（最终回答前 200 字）
- session_id：来源会话
- created_at：创建时间

不引入向量检索和 confidence 打分，避免过度设计。
关键词子串匹配即可在 3 篇论文规模下达到足够效果。
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class MemoryStore:
    """跨会话长期记忆存储，基于 JSON 文件"""

    def __init__(self, file_path: str | Path):
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memories: list[dict] = []
        self._load()

    def _load(self) -> None:
        """从磁盘加载记忆"""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._memories = data.get("memories", [])
            except (json.JSONDecodeError, OSError):
                self._memories = []
        else:
            self._memories = []

    def _save(self) -> None:
        """持久化到磁盘"""
        data = {"memories": self._memories}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, key: str, content: str, session_id: str) -> None:
        """
        保存一条记忆。如果 key 与已有记忆重叠率 >= overlap_ratio，则覆盖。

        Args:
            key: 主题关键词（例如：'MIM-Reasoner 方法'）
            content: 记忆内容（前 200 字）
            session_id: 来源会话 ID
        """
        now = datetime.now(timezone.utc).isoformat()

        # 检查是否有同一主题的记忆
        for i, mem in enumerate(self._memories):
            if self._key_overlap(key, mem["key"]) >= 0.5:
                self._memories[i] = {
                    "key": key,
                    "content": content,
                    "session_id": session_id,
                    "created_at": mem["created_at"],  # 保留首次创建时间
                    "updated_at": now,
                }
                self._save()
                return

        # 新增记忆
        new_mem = {
            "key": key,
            "content": content,
            "session_id": session_id,
            "created_at": now,
        }
        self._memories.append(new_mem)

        # 超过上限时丢弃最旧的
        max_entries = 50
        if len(self._memories) > max_entries:
            self._memories = self._memories[-max_entries:]

        self._save()

    def search(self, keyword: str) -> list[dict]:
        """
        按关键词子串匹配搜索记忆

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的记忆条目列表，按更新时间降序
        """
        keyword_lower = keyword.lower()
        results = []
        for mem in self._memories:
            if (
                keyword_lower in mem["key"].lower()
                or keyword_lower in mem["content"].lower()
            ):
                results.append(mem)

        # 按更新时间降序（最新的在前）
        results.sort(
            key=lambda m: m.get("updated_at", m["created_at"]),
            reverse=True,
        )
        return results

    def load(self) -> list[dict]:
        """返回全部记忆"""
        return list(self._memories)

    def delete(self, key: str) -> bool:
        """按 key 删除记忆"""
        before = len(self._memories)
        self._memories = [m for m in self._memories if m["key"] != key]
        if len(self._memories) < before:
            self._save()
            return True
        return False

    @staticmethod
    def _key_overlap(key1: str, key2: str) -> float:
        """
        计算两个 key 的词级别重叠率

        取两个 key 的共同词数 / 较长 key 的词数。
        适合中英文混合场景。
        """
        if not key1 or not key2:
            return 0.0
        # 按非字母数字分隔取词（含中文）
        words1 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key1.lower()))
        words2 = set(re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]+', key2.lower()))
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        return len(intersection) / max(len(words1), len(words2))


# 全局单例，默认存储路径
DEFAULT_MEMORY_PATH = Path("output") / "sessions" / "memory_store.json"
memory_store = MemoryStore(DEFAULT_MEMORY_PATH)
