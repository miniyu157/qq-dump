"""数据库连接与映射解析的底层封装。"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from schema import Table
from schema.databases import for_file

from .errors import DatabaseError


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    """以只读模式打开数据库，退出时关闭；打开与查询期间的 sqlite 错误转为 DatabaseError。"""
    # 损坏或非数据库文件在首次查询时才报错，因此查询期间的错误也需要转换
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"无法打开数据库: {path}: {exc}") from exc
    try:
        yield conn
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"无法读取数据库: {path}: {exc}") from exc
    finally:
        conn.close()


def table_map(db_path: str, table: str) -> Table:
    """按库文件名与表名取映射，未登记抛 DatabaseError"""
    mapping = for_file(db_path, table)
    if mapping is None:
        raise DatabaseError(f"未登记的映射: {Path(db_path).name} 中的 {table}，文件名需保持原始库名，如 profile_info.db")
    return mapping


def resolve_column(table: Table, name: str) -> str:
    """语义名称对应的列号，未登记抛 KeyError"""
    column = table.column_id(name)
    if column is None:
        raise KeyError(f"未登记的列: {name}")
    return column


def resolve_field(table: Table, column: str, name: str) -> int:
    """列下 protobuf 字段名称对应的字段号，未登记抛 KeyError"""
    field = table.field_id(column, name)
    if field is None:
        raise KeyError(f"未登记的字段: {name}")
    return field


def uid_set(conn: sqlite3.Connection, table: Table) -> set[str]:
    """读取表中语义名为 uid 的列，返回 UID 集合"""
    column = resolve_column(table, "uid")
    return {row[0] for row in conn.execute(f"SELECT [{column}] FROM [{table.name}]")}
