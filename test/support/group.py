"""明文 group_info.db 样本与手写的期望结果。

表结构与字段号取自实机数据库；每条期望值按「群资料」的语义手写，不经被测代码生成。
每一行各对应一种情形，见 populate_group 内的注释。
"""

import sqlite3
from pathlib import Path

from support.wire import field

__all__ = ["BULLETINS", "DETAILS", "ESSENCES", "MEMBERS", "NOTICES", "write_group"]

GROUP_A = 10001
GROUP_B = 10002
GROUP_C = 10003

# 只有扩展信息行、没有资料行的群，用于确认详情只按资料表列出
GROUP_WITHOUT_DETAIL = 10004

_LEVELS = field(67103, field(67200, 1) + field(67201, "潜水".encode())) + field(67103, field(67200, 2) + field(67201, "冒泡".encode()))

DETAILS = [
    {
        "group_code": GROUP_A,
        "group_name": "测试群甲",
        "remark": "我的备注",
        "owner_uid": "u_owner_a",
        "owner_uin": 30001,
        "create_time": 1600000000,
        "member_count": 2,
        "max_member_count": 200,
        "pinned_announce": "置顶公告",
        "description": "群简介",
        "labels": "游戏",
        "entrance_q": "入群问题",
        "leave_flag": 0,
        "leave_flag_name": "在群",
        "activity_score": 42,
        "period_msg_count": 1024,
        "lucky_char_content": "yyds",
        "custom_labels": [
            {"group_code": GROUP_A, "label_id": "label-1", "content": "标签一", "setter_uid": "u_owner_a", "set_time": 1610000000},
        ],
        "address": {"setter_uid": "u_owner_a", "set_time": 1610000001, "location_id": 9, "longitude": 116400000, "latitude": 39900000, "location_name": "北京"},
    },
    {
        "group_code": GROUP_B,
        "group_name": "测试群乙",
        "remark": "",
        "owner_uid": "u_owner_b",
        "owner_uin": None,
        "create_time": 0,
        "member_count": 0,
        "max_member_count": 0,
        "pinned_announce": None,
        "description": None,
        "labels": "",
        "entrance_q": "",
        "leave_flag": 0,
        "leave_flag_name": "在群",
        "activity_score": None,
        "period_msg_count": None,
        "lucky_char_content": "",
        "custom_labels": [],
        "address": None,
    },
    {
        "group_code": GROUP_C,
        "group_name": "已退出的群",
        "remark": "",
        "owner_uid": "",
        "owner_uin": None,
        "create_time": 0,
        "member_count": 0,
        "max_member_count": 0,
        "pinned_announce": None,
        "description": None,
        "labels": "",
        "entrance_q": "",
        "leave_flag": 1,
        "leave_flag_name": "已退群",
        "activity_score": None,
        "period_msg_count": None,
        "lucky_char_content": "",
        "custom_labels": [],
        "address": None,
    },
]

MEMBERS = [
    {
        "group_code": GROUP_A, "uid": "u_owner_a", "uin": 30001, "card": "", "nickname": "群主甲", "join_time": 1600000001, "last_speak_time": 1700000000,
        "mute_until": 0, "admin_flag": 1, "admin_flag_name": "管理员", "member_flag": 0, "member_flag_name": "在群", "custom_title": "头衔甲", "member_level": 2, "level_name": "冒泡",
    },
    {
        "group_code": GROUP_A, "uid": "u_member_a2", "uin": 30002, "card": "群名片", "nickname": "成员甲二", "join_time": 1600000002, "last_speak_time": 0,
        "mute_until": 1700000100, "admin_flag": 0, "admin_flag_name": "成员", "member_flag": 0, "member_flag_name": "在群", "custom_title": "", "member_level": 1, "level_name": "潜水",
    },
]

# 已退群的成员默认不列出；等级未在配置中登记的成员，头衔为空
LEFT_MEMBER = {
    "group_code": GROUP_A, "uid": "u_left_a3", "uin": 30003, "card": "", "nickname": "已退成员", "join_time": 1600000003, "last_speak_time": 0,
    "mute_until": 0, "admin_flag": 0, "admin_flag_name": "成员", "member_flag": 1, "member_flag_name": "已退群", "custom_title": "", "member_level": 9, "level_name": None,
}

BULLETINS = [
    {"group_code": GROUP_A, "publisher_uid": "u_owner_a", "fid": "fid-a", "published_time": 1650000000, "updated_time": 1650000001, "text": "正文一\n正文二"},
    {"group_code": GROUP_B, "publisher_uid": "", "fid": "", "published_time": 0, "updated_time": 0, "text": ""},
]

ESSENCES = [
    {
        "group_code": GROUP_A, "msg_seq": 10, "msg_random": 20, "sender_uin": 30002, "sender_nickname": "成员甲二",
        "state": 1, "state_name": "当前精华", "operator_uin": 30001, "operator_nickname": "群主甲", "set_time": 1660000000,
    },
]

# 取消精华的行保留，默认不列出
CANCELLED_ESSENCE = {
    "group_code": GROUP_A, "msg_seq": 11, "msg_random": 21, "sender_uin": 30002, "sender_nickname": "成员甲二",
    "state": 2, "state_name": "已取消", "operator_uin": 30001, "operator_nickname": "群主甲", "set_time": 1660000001,
}

NOTICES = [
    {
        "group_code": GROUP_A, "group_name": "测试群甲", "event": 1, "event_name": "申请入群", "state": 1, "state_name": "待处理",
        "operated": {"uid": "u_applicant", "nickname": "申请人"}, "operator": None,
        "created_time": 1670000000000, "operate_time": 0, "remark": "申请留言", "system_remark": "",
    },
    {
        "group_code": None, "group_name": "", "event": 6, "event_name": "被踢出", "state": 0, "state_name": "无需处理",
        "operated": {"uid": "u_kicked", "nickname": "被踢者"}, "operator": {"uid": "u_admin", "nickname": "管理员"},
        "created_time": 1660000000000, "operate_time": 1660000001, "remark": "", "system_remark": "系统附言",
    },
]


def write_group(path: Path) -> None:
    """在 path 写出明文 group_info.db，内容见 populate_group。"""
    conn = sqlite3.connect(path)
    try:
        populate_group(conn)
        conn.commit()
    finally:
        conn.close()


def populate_group(conn: sqlite3.Connection) -> None:
    """在 conn 上建表并写入对应上述期望值的数据，不提交。"""
    for statement in (
        'CREATE TABLE group_detail_info_ver1 ("60001" INTEGER, "60002" TEXT, "60004" INTEGER, "60005" INTEGER, "60006" INTEGER, "60007" TEXT, "60026" TEXT, "60216" TEXT, "60217" TEXT, "60218" TEXT, "60224" TEXT, "60340" INTEGER, "60241" BLOB, "60242" BLOB)',
        'CREATE TABLE group_ext_list ("60001" INTEGER, "66720" INTEGER, "66726" INTEGER, "66723" TEXT, "66732" BLOB)',
        'CREATE TABLE group_member3 ("60001" INTEGER, "1000" TEXT, "1002" INTEGER, "20002" TEXT, "64003" TEXT, "64007" INTEGER, "64008" INTEGER, "64009" INTEGER, "64010" INTEGER, "64016" INTEGER, "64023" TEXT, "64035" INTEGER)',
        'CREATE TABLE group_member_level_info ("60001" INTEGER, "67100" INTEGER, "67103" BLOB)',
        'CREATE TABLE group_bulletin ("60001" INTEGER, "64205" BLOB)',
        'CREATE TABLE group_essence ("60001" INTEGER, "67501" INTEGER, "67502" INTEGER, "67503" INTEGER, "67504" TEXT, "67505" INTEGER, "67506" INTEGER, "67507" TEXT, "67508" INTEGER)',
        'CREATE TABLE group_notify_list ("61001" INTEGER, "61002" INTEGER, "61003" INTEGER, "61004" BLOB, "61005" BLOB, "61007" BLOB, "61008" INTEGER, "61010" TEXT, "61011" TEXT)',
    ):
        conn.execute(statement)

    # 群甲: 各字段齐全，带一条自定义标签与群地址；公告正文两段，另有一个「群公告」标题项应被跳过
    labels = field(60241, field(60001, GROUP_A) + field(60121, b"u_owner_a") + field(60122, b"label-1") + field(60123, 1610000000) + field(60127, "标签一".encode()))
    address = field(60242, field(60131, b"u_owner_a") + field(60132, 1610000001) + field(60133, 9) + field(60134, 116400000) + field(60135, 39900000) + field(60136, "北京".encode()))
    # 群乙: 公告只有标题项，没有正文
    detail_rows = [
        (GROUP_A, "u_owner_a", 1600000000, 200, 2, "测试群甲", "我的备注", "置顶公告", "群简介", "游戏", "入群问题", 0, labels, address),
        (GROUP_B, "u_owner_b", 0, 0, 0, "测试群乙", "", None, None, "", "", 0, None, None),
        (GROUP_C, "", 0, 0, 0, "已退出的群", "", None, None, "", "", 1, None, None),
    ]
    conn.executemany('INSERT INTO group_detail_info_ver1 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', detail_rows)

    # 群甲有活跃度与群主 uin，群乙没有扩展信息，另有一个群只有扩展信息行
    conn.executemany('INSERT INTO group_ext_list VALUES (?,?,?,?,?)', [
        (GROUP_A, 42, 1024, "yyds", field(66732, field(60002, b"u_owner_a") + field(66530, 30001))),
        (GROUP_WITHOUT_DETAIL, 0, 0, "", None),
    ])

    conn.executemany('INSERT INTO group_member3 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
        (GROUP_A, "u_owner_a", 30001, "群主甲", "", 1600000001, 1700000000, 0, 1, 0, "头衔甲", 2),
        (GROUP_A, "u_member_a2", 30002, "成员甲二", "群名片", 1600000002, 0, 1700000100, 0, 0, "", 1),
        (GROUP_A, "u_left_a3", 30003, "已退成员", "", 1600000003, 0, 0, 0, 1, "", 9),
    ])
    conn.execute('INSERT INTO group_member_level_info VALUES (?,?,?)', (GROUP_A, 0, _LEVELS))

    # 正文类型 0、标题类型 10；正文项没有 text 时不应产生空行
    bulletin_body = field(64205, field(60001, GROUP_A) + field(64202, field(64221, b"u_owner_a") + field(64223, b"fid-a") + field(64225, 1650000000) + field(64226, 1650000001) + field(64227, field(64241, 0) + field(64242, field(64451, 0) + field(64452, "正文一".encode())) + field(64242, field(64451, 10) + field(64452, "群公告".encode())) + field(64242, field(64451, 0) + field(64452, "正文二".encode())))))
    conn.executemany('INSERT INTO group_bulletin VALUES (?,?)', [(GROUP_A, bulletin_body), (GROUP_B, field(64205, field(60001, GROUP_B) + field(64202, field(64227, field(64242, field(64451, 10) + field(64452, "群公告".encode()))))))])

    conn.executemany('INSERT INTO group_essence VALUES (?,?,?,?,?,?,?,?,?)', [
        (GROUP_A, 10, 20, 30002, "成员甲二", 1, 30001, "群主甲", 1660000000),
        (GROUP_A, 11, 21, 30002, "成员甲二", 2, 30001, "群主甲", 1660000001),
    ])

    group_info = field(61004, field(60001, GROUP_A) + field(60007, "测试群甲".encode()))
    applicant = field(61005, field(1000, b"u_applicant") + field(20002, "申请人".encode()))
    conn.executemany('INSERT INTO group_notify_list VALUES (?,?,?,?,?,?,?,?,?)', [
        (1670000000000, 1, 1, group_info, applicant, None, 0, "申请留言", ""),
        (1660000000000, 6, 0, None, field(61005, field(1000, b"u_kicked") + field(20002, "被踢者".encode())), field(61007, field(1000, b"u_admin") + field(20002, "管理员".encode())), 1660000001, "", "系统附言"),
    ])
