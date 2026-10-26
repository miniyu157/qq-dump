"""好友信息查询: 候选 UID 取 profile_info_v6 的 20001 非 0 非 null 行，是否好友由 buddy_list 判定。"""

import sqlite3
from collections.abc import Collection, Mapping
from typing import NamedTuple

from lib.wire import parse_fields
from schema import Table

from .categories import group_names, owner_uid
from .database import connect, resolve_column, resolve_field, table_map, uid_set


class Friend(NamedTuple):
    """好友信息快照；gender 保留原始值，gender_name、密友关系与分组为映射名称；is_friend 由 buddy_list 判定，deletion_time 仅非好友取 20001 时间戳；主人自身固定为非好友且无删除时间"""

    uid: str
    uin: int | None
    qid: str | None
    nickname: str | None
    remark: str | None
    signature: str | None
    birth_year: int | None
    birth_month: int | None
    birth_day: int | None
    age: int | None
    gender: int | None
    gender_name: str | None
    intimacy: int | None
    close_relation: str | None
    group_id: int | None
    group_name: str | None
    is_friend: bool
    is_bot: bool
    deletion_time: int | None


FIELDS = (
    "uid",
    "uin",
    "qid",
    "nickname",
    "remark",
    "signature",
    "birth_year",
    "birth_month",
    "birth_day",
    "age",
    "gender",
    "intimacy",
    "close_relation",
    "group_id",
    "deletion_time",
)


class _Related(NamedTuple):
    """构造 Friend 需要的关联数据: 好友 UID、机器人 UID 与分组名称"""

    buddies: Collection[str]
    bots: Collection[str]
    groups: Mapping[int, str]


def load_friends(db_path: str) -> list[Friend]:
    """按 rowid 顺序返回 20001 非 0 非 null 的 profile 行，标记好友、非好友与机器人"""
    table = table_map(db_path, "profile_info_v6")
    columns = _profile_columns(table)
    deletion = columns["deletion_time"]
    where = f"WHERE [{deletion}] IS NOT NULL AND [{deletion}] != 0"
    with connect(db_path) as conn:
        related = _related(conn, db_path)
        return [_build_friend(table, columns, values, related) for values in _profile_rows(conn, table, columns, where)]


def load_owner(db_path: str) -> Friend | None:
    """按主人 UID 查询 profile_info_v6，返回主人 Friend；UID 或资料行缺失时返回 None"""
    table = table_map(db_path, "profile_info_v6")
    columns = _profile_columns(table)
    with connect(db_path) as conn:
        uid = owner_uid(conn, table_map(db_path, "category_list_v2"))
        if uid is None:
            return None
        rows = _profile_rows(conn, table, columns, f"WHERE [{columns['uid']}] = ?", (uid,))
        if not rows:
            return None
        return _build_friend(table, columns, rows[0], _related(conn, db_path), self_profile=True)


def _related(conn: sqlite3.Connection, db_path: str) -> _Related:
    return _Related(
        buddies=uid_set(conn, table_map(db_path, "buddy_list")),
        bots=uid_set(conn, table_map(db_path, "profile_info_adelie")),
        groups=group_names(conn, table_map(db_path, "category_list_v2")),
    )


def _profile_columns(table: Table) -> dict[str, str]:
    """语义字段名到 profile_info_v6 列号的映射"""
    return {name: resolve_column(table, name) for name in FIELDS}


def _profile_rows(conn: sqlite3.Connection, table: Table, columns: Mapping[str, str], where: str, params: tuple = ()) -> list[dict[str, object]]:
    """按 where 查询 profile 行，按 rowid 顺序返回 语义字段名 -> 值"""
    select = ", ".join(f"[{column}]" for column in columns.values())
    sql = f"SELECT {select} FROM [{table.name}] {where} ORDER BY rowid"
    return [dict(zip(FIELDS, row)) for row in conn.execute(sql, params)]


def _build_friend(table: Table, columns: Mapping[str, str], values: Mapping[str, object], related: _Related, *, self_profile: bool = False) -> Friend:
    """把 profile 行转换为 Friend；self_profile 为主人自身，固定非好友且无删除时间"""
    uid = values["uid"]
    is_friend = False if self_profile else uid in related.buddies
    return Friend(
        uid=uid,
        uin=values["uin"],
        qid=values["qid"],
        nickname=values["nickname"],
        remark=values["remark"],
        signature=values["signature"],
        birth_year=values["birth_year"],
        birth_month=values["birth_month"],
        birth_day=values["birth_day"],
        age=values["age"],
        gender=values["gender"],
        gender_name=table.columns[columns["gender"]].enum.get(values["gender"]),
        intimacy=values["intimacy"],
        close_relation=_decode_relation(table, columns["close_relation"], values["close_relation"]),
        group_id=values["group_id"],
        group_name=related.groups.get(values["group_id"]),
        is_friend=is_friend,
        is_bot=uid in related.bots,
        deletion_time=None if self_profile or is_friend else values["deletion_time"] or None,
    )


def _decode_relation(table: Table, column: str, blob: bytes | None) -> str | None:
    """解析密友关系: 优先当前展示 ID，缺失时取预设列表首项，再映射为名称"""
    if not blob:
        return None

    # blob 外层是以列号为字段号的消息，关系对象位于该字段内
    payload = next((value for number, wire, value in parse_fields(blob) or [] if number == int(column) and wire == "bytes"), None)
    if payload is None:
        return None

    fields = parse_fields(payload) or []
    current = resolve_field(table, column, "current_relation_id")
    preset = resolve_field(table, column, "preset_relation_ids")
    numbers = [value for number, wire, value in fields if number == current and wire == "varint"]
    if not numbers:
        numbers = [value for number, wire, value in fields if number == preset and wire == "varint"]
    if not numbers:
        return None
    return table.enum(f"{column}.{current}", numbers[0])
