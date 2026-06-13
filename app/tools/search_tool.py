"""
SearXNG 网络搜索工具模块

替代原有的 Tavily 搜索，使用自托管的 SearXNG 实例。
SearXNG 聚合 DuckDuckGo、Google、Bing 等多种搜索引擎，
无需 API Key，零额度限制。

SearXNG 默认地址为 docker 内 http://searxng:8080
也可以通过环境变量 SEARXNG_BASE_URL 覆盖。
"""

import json
import os
from typing import Any, Literal

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

from app.api.monitor import monitor

load_dotenv()

SEARXNG_BASE_URL = os.getenv(
    "SEARXNG_BASE_URL",
    os.getenv("SEARXNG_BASE_URL_DOCKER", "http://searxng:8080"),
)


@tool
def internet_search(
    query: str,
    topic: Literal["news", "finance", "general"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
) -> str:
    """
    根据用户问题检索互联网公开信息

    通过自托管的 SearXNG 实例聚合多搜索引擎结果。
    注意：本工具只用于外部公开网页、新闻、论文主页、代码仓库等信息，
    不用于查询 MySQL 元数据或本地论文库正文。
    :param query: 搜索关键词或自然语言问题
    :param topic: 搜索主题（general/news/finance），映射到 SearXNG categories
    :param max_results: 返回的最大结果数
    :param include_raw_content: 是否尝试获取网页正文（SearXNG 可能不返回完整正文）
    :return: 结构化搜索结果 JSON 字符串
    """
    monitor.report_tool(
        tool_name="网络搜索工具(SearXNG)",
        args={
            "query": query,
            "topic": topic,
            "max_results": max_results,
        },
    )

    # 映射 topic 到 SearXNG category
    category_map = {
        "general": "general",
        "news": "news",
        "finance": "news",  # SearXNG 没有 finance 分类，用 news 替代
    }
    category = category_map.get(topic, "general")

    try:
        search_url = f"{SEARXNG_BASE_URL}/search"
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "categories": category,
            "pageno": 1,
        }

        resp = requests.get(
            search_url,
            params=params,
            timeout=5,
            headers={"User-Agent": "DeepSearch-Agent/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        # 按 max_results 截断
        results = results[:max_results]

        if not results:
            return f"未搜索到与「{query}」相关的结果。可尝试更换关键词或减少精度。\n（提示：如果 SearXNG 容器刚启动，首次搜索可能需要几秒钟初始化）"

        parts = []
        for i, r in enumerate(results, start=1):
            title = r.get("title", "无标题")
            url = r.get("url", "")
            content = r.get("content", "")
            # include_raw_content 为 True 时尝试取 engine 返回的完整文本
            if include_raw_content:
                content = r.get("raw_content", "") or content
            snippet = " ".join(content.split())[:500] if content else "无摘要"
            source = r.get("engine", "unknown")

            parts.append(
                f"[结果{i}] {title}\n"
                f"  链接: {url}\n"
                f"  来源引擎: {source}\n"
                f"  摘要: {snippet}\n"
            )

        return "\n".join(parts)

    except requests.exceptions.ConnectionError:
        return (
            f"无法连接到 SearXNG 实例 ({SEARXNG_BASE_URL})。\n"
            f"请确认 SearXNG 容器已启动：\n"
            f"  docker compose -f docker/docker-compose.yaml up -d searxng\n"
            f"或者检查 SEARXNG_BASE_URL 环境变量是否正确。"
        )
    except requests.exceptions.Timeout:
        return f"SearXNG 搜索超时，请稍后重试。查询词：{query}"
    except Exception as exc:
        return f"网络搜索异常：{str(exc)}"


if __name__ == "__main__":
    result = internet_search.invoke(
        {"query": "多层网络影响力最大化 2024", "max_results": 3}
    )
    print(result)
