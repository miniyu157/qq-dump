"""表的行数据。"""

import sqlite3
from typing import NamedTuple

from db._sql import quote_identifier

__all__ = ["Rows", "table_rows"]


class Rows(NamedTuple):
    """names 为列名，不含 rowid；row_ids 与 values 逐行对应，values 的每行与 names 一一对应，值保持 SQLite 返回的原始类型。"""

    names: list[str]
    row_ids: list[int]
    values: list[tuple]


def table_rows(conn: sqlite3.Connection, table: str, *, last: int | None) -> Rows:
    """按 rowid 升序返回行；last 为 None 时返回全表，否则只返回 rowid 最大的 last 行。

    表必须存在且带 rowid，调用前先用 schema.columns 确认表存在。
    """
    sql = f"SELECT rowid, * FROM {quote_identifier(table)} ORDER BY rowid"
    if last is None:
        cursor = conn.execute(sql)
        fetched = cursor.fetchall()
    else:
        cursor = conn.execute(f"{sql} DESC LIMIT ?", (last,))
        fetched = cursor.fetchall()[::-1]
    return Rows([item[0] for item in cursor.description[1:]], [row[0] for row in fetched], [row[1:] for row in fetched])
