"""数据库结构发现 —— 从 SQLite 数据库文件中提取表和列的元数据。

API:
    get_tables_by_files(*paths) -> list[str]
    get_columns_by_files(*paths, table) -> list[DBColumn]
"""

from __future__ import annotations

import re
import sqlite3

from .types import DBColumn

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_FTS_SUFFIXES = (
    "_fts",
    "_fts_data",
    "_fts_idx",
    "_fts_docsize",
    "_fts_config",
)


def _is_user_table(name: str) -> bool:
    """过滤 SQLite 内部表和 FTS 辅助表。"""
    if name.startswith("sqlite_"):
        return False
    if name.endswith(_FTS_SUFFIXES):
        return False
    return True


def get_tables_by_files(*paths: str) -> list[str]:
    """从指定的数据库文件中获取所有用户表名的并集。

    FTS 辅助表和 sqlite_* 内部表会被过滤。

    Args:
        *paths: 一个或多个数据库文件路径

    Returns:
        去重后的表名列表
    """
    names: set[str] = set()

    for path in paths:
        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (name,) in rows:
            if _is_user_table(name):
                names.add(name)

    return sorted(names)


def get_columns_by_files(*paths: str, table: str) -> list[DBColumn]:
    """从指定的数据库文件中获取某个表在所有文件中的列的并集。

    按列名去重。若某文件中不存在该表，静默跳过。

    Args:
        *paths: 一个或多个数据库文件路径
        table: 目标表名

    Returns:
        合并去重后的 DBColumn 列表
    """
    if not _IDENTIFIER_RE.match(table):
        raise ValueError(f"非法的表名 {table!r}：必须是合法的 SQL 标识符")

    merged: dict[str, DBColumn] = {}

    for path in paths:
        with sqlite3.connect(path) as conn:
            cols = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            if not cols:
                continue
            for _, name, col_type, *_ in cols:
                if name not in merged:
                    merged[name] = DBColumn(name=name, col_type=col_type)

    return list(merged.values())
