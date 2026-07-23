"""好友分组查询 —— category_list_v2 protobuf 解码。

API:
    list_groups(db) -> list[FriendGroup]

每个函数接受 str（DB 路径）或已打开的 sqlite3.Connection。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .proto import decode_proto_field
from .schema.profile_info.category import CATEGORY_LIST_V2
from .types.group import FriendGroup

_GI = CATEGORY_LIST_V2.column("group_info")


@contextmanager
def _using(db: str | sqlite3.Connection):
    """统一连接管理：str → 新建并关闭，Connection → 直接复用。"""
    if isinstance(db, sqlite3.Connection):
        yield db
    else:
        with sqlite3.connect(db) as conn:
            yield conn


# ═══════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════


def list_groups(db: str | sqlite3.Connection) -> list[FriendGroup]:
    """列出所有好友分组。"""
    with _using(db) as conn:
        row = conn.execute(
            f'SELECT "{_GI.id}" FROM category_list_v2 LIMIT 1'
        ).fetchone()
        if row is None or row[0] is None:
            return []
        return decode_proto_field(row[0], _GI, FriendGroup)
