"""好友信息查询：UID 列表来自 buddy_list，完整信息来自 profile_info_v6。"""

import sqlite3
from collections.abc import Collection, Mapping
from contextlib import closing
from typing import NamedTuple

from lib.wire import parse_fields
from schema import Table

from .bots import _bot_uids
from .categories import _group_names, owner_uid
from .database import open_db, resolve_column, resolve_field, table_map


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


def _friend_uids(conn: sqlite3.Connection, table: Table) -> set[str]:
    """读取 buddy_list 的 uid 列，返回好友 UID 集合"""
    column = resolve_column(table, "uid")
    return {row[0] for row in conn.execute(f"SELECT [{column}] FROM [{table.name}]")}


def _profile_columns(table: Table) -> dict[str, str]:
    """语义字段名到 profile_info_v6 列号的映射"""
    return {name: resolve_column(table, name) for name in FIELDS}


def _build_friend(table: Table, columns: Mapping[str, str], values: Mapping[str, object], buddies: Collection[str], bots: Collection[str], groups: Mapping[int, str], *, self_profile: bool = False) -> Friend:
    """把 profile 行转换为 Friend；self_profile 为主人自身，固定非好友且无删除时间"""
    relation_column = columns["close_relation"]
    uid = values["uid"]
    is_friend = False if self_profile else uid in buddies
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
        close_relation=_decode_relation(table, relation_column, values["close_relation"]),
        group_id=values["group_id"],
        group_name=groups.get(values["group_id"]),
        is_friend=is_friend,
        is_bot=uid in bots,
        deletion_time=None if self_profile or is_friend else values["deletion_time"] or None,
    )


def _friend_profiles(conn: sqlite3.Connection, table: Table, buddies: Collection[str], bots: Collection[str], groups: Mapping[int, str]) -> list[Friend]:
    """查询 20072 非空的 profile 行，按 rowid 顺序返回，标记好友、非好友与机器人；非好友取 20001 作为删除时间"""
    columns = _profile_columns(table)
    select = ", ".join(f"[{column}]" for column in columns.values())
    sql = f"SELECT {select} FROM [{table.name}] WHERE [{columns['close_relation']}] IS NOT NULL ORDER BY rowid"
    return [
        _build_friend(table, columns, dict(zip(FIELDS, row)), buddies, bots, groups)
        for row in conn.execute(sql)
    ]


def _decode_relation(table: Table, column: str, blob: bytes | None) -> str | None:
    """解析密友关系：优先当前展示 ID，缺失时取预设列表首项，再映射为名称"""
    if not blob:
        return None

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


def load_friends(db_path: str) -> list[Friend]:
    buddy_table = table_map(db_path, "buddy_list")
    profile_table = table_map(db_path, "profile_info_v6")
    category_table = table_map(db_path, "category_list_v2")
    bot_table = table_map(db_path, "profile_info_adelie")
    with closing(open_db(db_path)) as conn:
        groups = _group_names(conn, category_table)
        return _friend_profiles(conn, profile_table, _friend_uids(conn, buddy_table), _bot_uids(conn, bot_table), groups)


def load_owner(db_path: str) -> Friend | None:
    """按主人 UID 查询 profile_info_v6，返回主人 Friend；UID 或资料行缺失时返回 None"""
    uid = owner_uid(db_path)
    if uid is None:
        return None

    profile_table = table_map(db_path, "profile_info_v6")
    columns = _profile_columns(profile_table)
    select = ", ".join(f"[{column}]" for column in columns.values())
    sql = f"SELECT {select} FROM [{profile_table.name}] WHERE [{columns['uid']}] = ? ORDER BY rowid LIMIT 1"
    with closing(open_db(db_path)) as conn:
        row = conn.execute(sql, (uid,)).fetchone()
        if row is None:
            return None
        buddies = _friend_uids(conn, table_map(db_path, "buddy_list"))
        bots = _bot_uids(conn, table_map(db_path, "profile_info_adelie"))
        groups = _group_names(conn, table_map(db_path, "category_list_v2"))
        return _build_friend(profile_table, columns, dict(zip(FIELDS, row)), buddies, bots, groups, self_profile=True)
