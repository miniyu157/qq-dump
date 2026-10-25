"""机器人资料：profile_info_adelie 的 UID 集合。"""

import sqlite3

from schema import Table

from .database import resolve_column


def _bot_uids(conn: sqlite3.Connection, table: Table) -> set[str]:
    """读取 profile_info_adelie 的 uid 列，返回机器人 UID 集合"""
    column = resolve_column(table, "uid")
    return {row[0] for row in conn.execute(f"SELECT [{column}] FROM [{table.name}]")}
