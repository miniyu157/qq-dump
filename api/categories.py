"""分类表数据：主人 UID 与分组名称解析。"""

import sqlite3
from contextlib import closing

from lib.wire import parse_fields
from schema import Table

from .database import open_db, resolve_column, resolve_field, table_map


def owner_uid(db_path: str) -> str | None:
    """返回数据库中的主人 UID；表为空时返回 None"""
    table = table_map(db_path, "category_list_v2")
    column = resolve_column(table, "owner_uid")
    with closing(open_db(db_path)) as conn:
        row = conn.execute(f"SELECT [{column}] FROM [{table.name}] ORDER BY rowid LIMIT 1").fetchone()
    return row[0] if row else None


def _group_names(conn: sqlite3.Connection, table: Table) -> dict[int, str]:
    """解析分组对象，返回 分组ID -> 分组名称"""
    column = resolve_column(table, "group")
    id_field = resolve_field(table, column, "group_id")
    name_field = resolve_field(table, column, "group_name")

    names = {}
    for (blob,) in conn.execute(f"SELECT [{column}] FROM [{table.name}]"):
        if not blob:
            continue
        for number, wire, payload in parse_fields(blob) or []:
            if number != int(column) or wire != "bytes":
                continue
            fields = parse_fields(payload) or []
            group_id = next((value for num, field_wire, value in fields if num == id_field and field_wire == "varint"), None)
            raw_name = next((value for num, field_wire, value in fields if num == name_field and field_wire == "bytes"), None)
            if group_id is not None and raw_name is not None:
                names[group_id] = raw_name.decode("utf-8", errors="replace")
    return names
