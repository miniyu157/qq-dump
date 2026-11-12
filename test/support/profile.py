"""明文 profile_info.db 样本与手写的期望结果。

表结构与字段号取自实机数据库 (见 schema/ 的说明)；OWNER 与 FRIENDS 是按「好友信息」的语义逐条手写的期望值，
不经被测代码生成。每一行各对应一种情形，见 write_profile 内的注释。
"""

import sqlite3
from pathlib import Path

from support.wire import field

__all__ = ["FRIENDS", "OWNER", "OWNER_UID", "populate_profile", "write_profile"]

OWNER_UID = "u_owner"

_EMPTY = {"qid": None, "remark": None, "signature": None, "birth_year": 0, "birth_month": 0, "birth_day": 0, "age": 0, "intimacy": 0, "close_relation": None, "is_bot": False}

OWNER = {
    "uid": OWNER_UID, "uin": 10001, "qid": None, "nickname": "主人", "remark": None, "signature": "签名",
    "birth_year": 2000, "birth_month": 1, "birth_day": 1, "age": 25, "gender": 1, "gender_name": "男",
    "intimacy": 0, "close_relation": None, "group_id": 0, "group_name": "我的好友",
    "is_friend": False, "is_bot": False, "deletion_time": None,
}

FRIENDS = [
    {
        "uid": "u_friend_a", "uin": 21001, "qid": "qid_a", "nickname": "好友甲", "remark": "备注甲", "signature": None,
        "birth_year": 2001, "birth_month": 2, "birth_day": 3, "age": 24, "gender": 2, "gender_name": "女",
        "intimacy": 1314, "close_relation": "情侣", "group_id": 1, "group_name": "同学",
        "is_friend": True, "is_bot": False, "deletion_time": None,
    },
    {**_EMPTY, "uid": "u_deleted_b", "uin": 20002, "nickname": "已删除乙", "gender": 0, "gender_name": "未知", "group_id": 0, "group_name": "我的好友", "is_friend": False, "deletion_time": 1690000000},
    {**_EMPTY, "uid": "u_bot_c", "uin": 20003, "nickname": "机器人丙", "gender": 255, "gender_name": "秘密", "group_id": 0, "group_name": "我的好友", "is_friend": True, "is_bot": True, "deletion_time": None},
    {**_EMPTY, "uid": "u_friend_d", "uin": 21004, "nickname": "好友丁", "gender": 7, "gender_name": None, "close_relation": "闺蜜", "group_id": 9, "group_name": None, "is_friend": True, "deletion_time": None},
    {**_EMPTY, "uid": "u_friend_e", "uin": 21005, "nickname": "好友戊", "gender": 1, "gender_name": "男", "group_id": 1, "group_name": "同学", "is_friend": True, "deletion_time": None},
]

# 列顺序与下方 INSERT 一致
_COLUMNS = '"1000" TEXT, "1001" TEXT, "1002" INTEGER, "20001" INTEGER, "20002" TEXT, "20006" INTEGER, "20007" INTEGER, "20008" INTEGER, "20009" TEXT, "20011" TEXT, "20014" INTEGER, "20048" INTEGER, "20070" INTEGER, "20072" BLOB, "24103" INTEGER'


def write_profile(path: Path, *, extra_friends: int = 0) -> None:
    """在 path 写出明文 profile_info.db，内容见 populate_profile。"""
    conn = sqlite3.connect(path)
    try:
        populate_profile(conn, extra_friends=extra_friends)
        conn.commit()
    finally:
        conn.close()


def populate_profile(conn: sqlite3.Connection, *, extra_friends: int = 0) -> None:
    """在 conn 上建表并写入对应 OWNER 与 FRIENDS 的数据，不提交。

    extra_friends 在其后追加若干只有昵称的好友，供手动试用时填充列表；测试使用缺省的 0。
    """
    lovers = field(20072, field(20074, 1))
    preset_only = field(20072, field(20073, 2) + field(20073, 3))
    unknown_relation = field(20072, field(20074, 999))
    rows = [
        # 主人: 20001 为 0，不进好友列表
        (OWNER_UID, None, 10001, 0, "主人", 2000, 1, 1, None, "签名", 1, 0, 0, None, 25),
        # 好友: 各字段齐全，当前密友关系为情侣
        ("u_friend_a", "qid_a", 21001, 1700000000, "好友甲", 2001, 2, 3, "备注甲", None, 2, 1, 1314, lovers, 24),
        # 不在 buddy_list: 已删除，20001 作为删除时间
        ("u_deleted_b", None, 20002, 1690000000, "已删除乙", 0, 0, 0, None, None, 0, 0, 0, None, 0),
        # 同时在 buddy_list 与机器人表
        ("u_bot_c", None, 20003, 1680000000, "机器人丙", 0, 0, 0, None, None, 255, 0, 0, None, 0),
        # 没有当前关系时取预设列表首项；性别与分组的取值未登记
        ("u_friend_d", None, 21004, 1700000004, "好友丁", 0, 0, 0, None, None, 7, 9, 0, preset_only, 0),
        # 关系 ID 未登记时不映射名称
        ("u_friend_e", None, 21005, 1700000005, "好友戊", 0, 0, 0, None, None, 1, 1, 0, unknown_relation, 0),
        # 20001 为 NULL 的资料行不是好友候选
        ("u_stranger_f", None, 20006, None, "路人己", 0, 0, 0, None, None, 0, 0, 0, None, 0),
    ]
    extras = [f"u_extra_{index:02d}" for index in range(1, extra_friends + 1)]
    rows += [(uid, None, 22000 + index, 1700001000 + index, f"好友{index:02d}", 0, 0, 0, None, None, 0, 0, 0, None, 0) for index, uid in enumerate(extras, 1)]

    for statement in ('CREATE TABLE buddy_list ("1000" TEXT)', 'CREATE TABLE profile_info_adelie ("1000" TEXT)', 'CREATE TABLE category_list_v2 ("1000" TEXT, "25011" BLOB)', f"CREATE TABLE profile_info_v6 ({_COLUMNS})"):
        conn.execute(statement)
    conn.executemany("INSERT INTO buddy_list VALUES (?)", [(uid,) for uid in ("u_friend_a", "u_bot_c", "u_friend_d", "u_friend_e", *extras)])
    conn.execute("INSERT INTO profile_info_adelie VALUES (?)", ("u_bot_c",))
    for group_id, name in ((0, "我的好友"), (1, "同学")):
        conn.execute("INSERT INTO category_list_v2 VALUES (?, ?)", (OWNER_UID, field(25011, field(25007, group_id) + field(25008, name.encode()))))
    conn.executemany(f"INSERT INTO profile_info_v6 VALUES ({', '.join('?' * 15)})", rows)
