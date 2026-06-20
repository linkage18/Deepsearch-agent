"""
文件路径解析工具

负责把模型或工具返回的虚拟路径、上传文件路径和相对路径统一转换为本地绝对路径
后续文件读取、Markdown 生成和 PDF 转换工具都可以复用这里的解析规则
"""

from pathlib import Path
from typing import Optional


def resolve_path(filename: str, session_dir: Optional[str] = None) -> str:
    """
    解析文件路径，并尽量把任务产物限制在当前会话目录中

    :param filename: 模型、工具或用户传入的文件名/路径
    :param session_dir: 当前任务的会话目录
    :return: 解析后的绝对路径
    """
    if not filename or not filename.strip():
        raise ValueError("文件名不能为空")

    path = Path(filename)
    path_str = filename.replace("\\", "/")

    # 大模型常返回 /workspace、/mnt/data 这类沙箱路径，本地项目需要先剥离虚拟前缀
    for prefix in ["/workspace", "/mnt/data", "/home/user"]:
        if path_str.startswith(prefix):
            cleaned = path_str[len(prefix) :].lstrip("/")
            path = Path(cleaned)
            path_str = str(path).replace("\\", "/")
            break

    if not session_dir:
        return str(path.resolve())

    session_path = Path(session_dir).resolve()
    session_name = session_path.name

    # 真实绝对路径只有在已经位于 session_dir 内时才允许保留。
    # 其他绝对路径统一降级为文件名，避免模型读取系统文件。
    if path.is_absolute():
        full_path = path.resolve()
        if _is_relative_to(full_path, session_path):
            return _fix_nested_session_path(full_path, session_path, session_name)
        path = Path(path.name)
        path_str = path.name

    parts = path.parts

    # 避免模型把 session 名或 output 前缀重复拼到当前会话目录里
    if session_name in parts:
        path = Path(path.name)

    if parts and parts[0] in {"output", "reports", "uploads", "updated"}:
        path = Path(path.name)

    full_path = (session_path / path).resolve()
    if not _is_relative_to(full_path, session_path):
        raise ValueError("拒绝访问：路径必须位于当前会话目录内")
    return str(full_path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _fix_nested_session_path(
    full_path: Path,
    session_path: Path,
    session_name: str,
) -> str:
    """
    修正 session_xxx/session_xxx/file.md 这类重复嵌套路径
    """
    parts = full_path.parts
    for index in range(len(parts) - 1):
        if parts[index] == session_name and parts[index + 1] == session_name:
            return str(session_path / full_path.name)
    return str(full_path)
