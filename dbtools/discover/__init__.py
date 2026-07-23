"""数据库结构发现 —— 从 SQLite 数据库文件中提取表和列的元数据。

API:
    get_tables_by_files(*paths) -> list[str]
    get_columns_by_files(*paths, table) -> list[DBColumn]
"""

from __future__ import annotations

from .sqlite import get_columns_by_files, get_tables_by_files
from .types import DBColumn, DBFile, DBTable

__all__ = ["DBColumn", "DBFile", "DBTable", "get_columns_by_files", "get_tables_by_files"]
