"""用户资料查询 —— profile_info_v6 核心操作。

API:
    get_by_uid(db, uid) -> AccountInfo | None
    get_my_info(db) -> AccountInfo | None

每个函数接受 str（DB 路径）或已打开的 sqlite3.Connection。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import MISSING, fields

from .schema.profile_info.profile import GENDER_MAP, PROFILE_INFO_V6
from .types.account import AccountInfo

_FIELDS = tuple(fields(AccountInfo))
_FNAMES = [f.name for f in _FIELDS]

_COL = {f.name: f'"{f.id}"' for f in PROFILE_INFO_V6.columns if f.name in set(_FNAMES)}
_SELECT = ", ".join(_COL[n] for n in _FNAMES)


@contextmanager
def _using(db: str | sqlite3.Connection):
    """统一连接管理：str → 新建并关闭，Connection → 直接复用。"""
    if isinstance(db, sqlite3.Connection):
        yield db
    else:
        with sqlite3.connect(db) as conn:
            yield conn


def _row_to_account(row: tuple) -> AccountInfo:
    """DB 行 → AccountInfo。

    NULL 值回退到 dataclass 声明的 default。
    gender 是唯一从 INTEGER 映射到语义字符串的字段。
    """
    kwargs: dict[str, object] = {}
    for field, value in zip(_FIELDS, row):
        if value is not None:
            kwargs[field.name] = value
        elif field.default is not MISSING:
            kwargs[field.name] = field.default
        else:
            kwargs[field.name] = None
    if isinstance(kwargs["gender"], int):
        kwargs["gender"] = GENDER_MAP.get(kwargs["gender"], "unset")
    return AccountInfo(**kwargs)


def _get_by_uid(conn: sqlite3.Connection, uid: str) -> AccountInfo | None:
    """在已有连接上按 UID 查询。"""
    row = conn.execute(
        f"SELECT {_SELECT} FROM profile_info_v6 WHERE {_COL['uid']} = ?", (uid,)
    ).fetchone()
    return _row_to_account(row) if row else None


# ═══════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════


def get_by_uid(db: str | sqlite3.Connection, uid: str) -> AccountInfo | None:
    """按 UID 查询用户信息。"""
    with _using(db) as conn:
        return _get_by_uid(conn, uid)


def get_my_info(db: str | sqlite3.Connection) -> AccountInfo | None:
    """查询主人账号信息（从 category_list_v2 获取 owner_uid）。"""
    with _using(db) as conn:
        row = conn.execute('SELECT "1000" FROM category_list_v2 LIMIT 1').fetchone()
        if row is None or row[0] is None:
            return None
        return _get_by_uid(conn, row[0])
