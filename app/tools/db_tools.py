"""
MySQL 数据库查询工具模块

封装数据库查询助手使用的三个 LangChain 工具：
list_sql_tables 用于发现真实表名，get_table_data 用于预览字段和样例数据，
execute_sql_query 用于在确认结构后执行自定义查询。
"""

import os
import re

from dotenv import load_dotenv
from langchain_core.tools import tool
from mysql.connector import Error, connect

from app.api.monitor import monitor

load_dotenv()

MAX_RESULT_ROWS = int(os.getenv("MYSQL_MAX_RESULT_ROWS", "100"))
MAX_EXECUTION_TIME_MS = int(os.getenv("MYSQL_MAX_EXECUTION_TIME_MS", "5000"))
READ_ONLY_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH")
FORBIDDEN_SQL_WORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "CALL",
    "LOAD",
    "SET",
}


# 集中读取数据库配置，后续三个工具都复用这份连接参数
def get_db_config():
    """
    从环境变量读取 MySQL 连接配置

    所有数据库工具都通过此函数拿到同一份连接参数，避免每个工具重复读取环境变量
    :return: mysql.connector.connect 可直接使用的连接参数
    """
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "collation": os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        "autocommit": True,
        "sql_mode": os.getenv("MYSQL_SQL_MODE", "TRADITIONAL"),
    }

    # 去掉未配置的可选项，避免把 None 传给 mysql.connector 造成连接参数异常
    config = {k: v for k, v in config.items() if v is not None}

    # user/password/database 是本教程工具能正常查询业务库的最小必要配置
    required_keys = ["user", "password", "database"]
    missing_keys = [k for k in required_keys if k not in config]
    if missing_keys:
        raise ValueError(f"缺失数据库核心配置：{', '.join(missing_keys)}")

    return config


def _strip_sql_comments(query: str) -> str:
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)
    query = re.sub(r"--[^\n\r]*", " ", query)
    query = re.sub(r"#[^\n\r]*", " ", query)
    return query.strip()


def _validate_readonly_sql(query: str) -> tuple[bool, str]:
    cleaned = _strip_sql_comments(query)
    if not cleaned:
        return False, "SQL 不能为空"
    if ";" in cleaned:
        return False, "拒绝执行：不允许多语句 SQL"

    sql_upper = cleaned.upper()
    if not sql_upper.startswith(READ_ONLY_PREFIXES):
        return False, "拒绝执行：只允许 SELECT/SHOW/DESCRIBE/EXPLAIN 查询"

    tokens = set(re.findall(r"\b[A-Z_]+\b", sql_upper))
    forbidden = sorted(tokens & FORBIDDEN_SQL_WORDS)
    if forbidden:
        return False, f"拒绝执行：SQL 中包含非只读关键字 {', '.join(forbidden)}"

    return True, cleaned


def _quote_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]+", str(identifier)):
        raise ValueError("表名只能包含字母、数字、下划线或中文")
    return f"`{str(identifier).replace('`', '``')}`"


def _fetch_table_names(cursor) -> set[str]:
    cursor.execute("SHOW TABLES")
    return {row[0] for row in cursor.fetchall()}


@tool
def list_sql_tables() -> str:
    """
    查询当前数据库中所有可用表

    作用：让模型先识别真实可用的表名，方便后续预览表结构和编写自定义 SQL。
    :return: 有表：可用的表有：表1,表2,表3...
             没有表：没有可用的表
             出现异常：查询出现异常：异常信息
    """

    # 埋点：工具一被调用，前端可以展示当前正在查询数据库表名
    monitor.report_tool(tool_name="数据库表名查询工具：list_sql_tables", args={})

    # 加载数据库连接信息
    config = get_db_config()

    # MySQL 查询的固定步骤：
    # 1. 创建连接
    # 2. 创建 cursor
    # 3. 执行 SQL
    # 4. 获取返回结果
    # 5. 释放连接和 cursor 资源
    # 这里捕获异常并返回中文提示，避免工具报错直接中断 Agent 执行链路
    try:
        # 使用 with 管理连接和游标，查询结束后自动释放数据库资源
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                tables = sorted(_fetch_table_names(cursor))

                # SHOW TABLES 返回形如：[("drugs",), ("inventory",), ("sales_records",)]
                if not tables:
                    return "没有可用的表"

                # 取每个元组的第一个元素，拼成模型容易阅读的表名列表
                return f"可用的表有：{', '.join(tables)}"
    except Error as e:
        return f"查询出现异常：{str(e)}"


@tool
def get_table_data(table_name) -> str:
    """
    查询指定表的前 100 行数据

    当前工具调用之前，应先调用 list_sql_tables 完成表名校验。
    此工具的作用：
    1. 完成单表样例数据查询
    2. 为多表查询提供表结构信息和数据格式参考
    :param table_name: 表名
    :return: CSV 格式数据
             1. 第一行是列信息，列之间使用英文逗号分隔
             2. 第二行开始是表数据，值之间也使用英文逗号分隔
             3. 行和行之间使用 \n 分隔
             4. 至多查询 100 条表数据
             例如：
                id,name,age\n -> 列头
                1,张三,18\n
                1,张三,18\n
                1,张三,18\n -> 至多查询 100 条
    """
    # 埋点：工具二被调用，前端可以展示当前正在预览哪张表
    monitor.report_tool(
        tool_name="数据库表数据查询工具：get_table_data",
        args={"table_name": table_name},
    )

    # 获取数据库参数
    config = get_db_config()

    # 查询流程同样是：连接 -> cursor -> 执行 SQL -> 获取列信息和数据 -> 自动释放资源
    try:
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                table_names = _fetch_table_names(cursor)
                if table_name not in table_names:
                    return f"拒绝查询：表 {table_name} 不在可用表白名单中。"

                safe_table_name = _quote_identifier(table_name)
                sql = f"SELECT * FROM {safe_table_name} LIMIT {MAX_RESULT_ROWS}"
                cursor.execute(sql)

                # cursor.description 保存查询结果的列元信息
                # 例如：[("id", ...), ("name", ...), ("age", ...)]
                # 如果 SQL 没有结果集，description 可能为 None
                description = cursor.description
                if not description:
                    return f"数据表 {table_name} 暂无数据。"

                # 只取每个列信息元组的第一个元素，也就是列名
                # 例如：["id", "name", "age"]
                columns = [desc[0] for desc in description]

                # fetchall 返回表数据，形如：[(1, "张三", 18), (2, "李四", 20)]
                rows = cursor.fetchall()

                # 把每一行数据从元组转成 CSV 行文本
                # 例如：(1, "张三", 18) -> "1,张三,18"
                results = [",".join(map(str, row)) for row in rows]

                # columns 组成 CSV 头部，rows 组成 CSV 数据体
                # 最终返回：
                # id,name,age
                # 1,张三,18
                header_str = ",".join(columns)
                data_str = "\n".join(results)
                return f"{header_str}\n{data_str}"
    except Error as e:
        return f"查询出现异常：{str(e)}"


@tool
def execute_sql_query(query) -> str:
    """
    执行自定义 SQL 查询

    切记：执行之前，需要通过 list_sql_tables 明确真实表名，
    再通过 get_table_data 明确表结构和数据格式。
    安全限制：只允许执行 SELECT/SHOW/WITH/DESCRIBE/EXPLAIN 开头的只读查询。
    切记：执行之前，需要通过 list_sql_tables 明确真实表名，
    再通过 get_table_data 明确表结构和数据格式。
    适合多表关联、筛选、聚合、排序等复杂查询。
    :param query: 要执行的自定义 SQL 语句
    :return: CSV 格式数据
    """
    valid, cleaned_query = _validate_readonly_sql(query)
    if not valid:
        return (
            f"{cleaned_query}。如需写入操作，请通过应用层接口完成。SQL 为: {query}"
        )

    # 埋点：记录模型最终生成的 SQL，便于教学时观察是否真的落到了正确表字段上
    monitor.report_tool(
        tool_name="数据库表数据查询工具：execute_sql_query", args={"query": query}
    )

    # 获取数据库参数
    config = get_db_config()

    # 自定义查询和 get_table_data 的结果处理逻辑一致：
    # 执行 SQL -> 读取 description 得到列名 -> fetchall 得到数据 -> 拼成 CSV 返回
    try:
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={MAX_EXECUTION_TIME_MS}")
                except Error:
                    pass
                # 工具层已做只读白名单校验，此处保留注释便于跟踪执行链路
                cursor.execute(cleaned_query)

                # 非查询类 SQL 没有结果集描述，这里统一返回提示，避免工具调用直接抛错给模型
                description = cursor.description
                if not description:
                    return f"执行自定义 SQL 语句没有查询结果，SQL 为：{query}"
                # description => [("列1", ...), ("列2", ...)]
                columns = [desc[0] for desc in description]

                # rows => [(值1, 值2), (值1, 值2)]
                rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
                truncated = len(rows) > MAX_RESULT_ROWS
                if truncated:
                    rows = rows[:MAX_RESULT_ROWS]

                # 每行元组统一转为逗号分隔文本，便于模型读取和后续整理
                results = [",".join(map(str, row)) for row in rows]

                # 第一行是列名，后续是查询数据
                header_str = ",".join(columns)
                data_str = "\n".join(results)
                suffix = (
                    f"\n[提示] 结果已截断，仅返回前 {MAX_RESULT_ROWS} 行。"
                    if truncated
                    else ""
                )
                return f"{header_str}\n{data_str}{suffix}"
    except Error as e:
        return f"查询出现异常：{str(e)}"


if __name__ == "__main__":
    # 本地调试入口：直接运行本文件可验证 .env 中的 MySQL 连接配置是否可用
    print(
        execute_sql_query.invoke(
            {
                "query": "SELECT * FROM `drugs` dgs join sales_records srd on dgs.drug_id = srd.drug_id"
            }
        )
    )
