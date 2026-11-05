"""主库的表与列。"""

import sqlite3
from typing import NamedTuple

from db._sql import quote_identifier

__all__ = ["ColumnInfo", "TableInfo", "columns", "tables"]


class TableInfo(NamedTuple):
    name: str
    rows: int


class ColumnInfo(NamedTuple):
    """pk 为该列在主键中的次序，从 1 开始；不属于主键时为 0。"""

    cid: int
    name: str
    type: str
    pk: int


def tables(conn: sqlite3.Connection) -> list[TableInfo]:
    """主库的表与虚拟表及其行数，按名称排序。FTS 影子表的 type 为 shadow，不在其中。"""
    names = [row[0] for row in conn.execute("SELECT name FROM pragma_table_list WHERE schema = 'main' AND type IN ('table', 'virtual') AND substr(name, 1, 7) <> 'sqlite_' ORDER BY name")]
    return [TableInfo(name, conn.execute(f"SELECT count(*) FROM {quote_identifier(name)}").fetchone()[0]) for name in names]


def columns(conn: sqlite3.Connection, table: str) -> list[ColumnInfo]:
    """表的列，表不存在时为空。xinfo 包含虚拟表的隐藏列。"""
    return [ColumnInfo(*row) for row in conn.execute("SELECT cid, name, type, pk FROM pragma_table_xinfo(?)", (table,))]
