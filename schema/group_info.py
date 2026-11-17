"""群资料库 group_info.db 的表结构。

列号与 protobuf 字段号来自实机数据库；各表以 60001 (group_code) 关联。
枚举值保留界面文案，未登记的取值不映射名称。
"""

from . import Column, ProtoField, Table

LEAVE_FLAGS = {0: "在群", 1: "已退群"}
ADMIN_FLAGS = {0: "成员", 1: "管理员"}
ESSENCE_STATES = {1: "当前精华", 2: "已取消"}

# 61002 的事件类型
NOTIFY_EVENTS = {
    1: "申请入群",
    3: "设为管理员",
    6: "被踢出",
    11: "申请被拒绝",
    13: "退群",
    15: "撤销管理员",
}

# 61003 的处理状态
NOTIFY_STATES = {0: "无需处理", 1: "待处理", 2: "已同意", 3: "已拒绝"}

group_detail_info_ver1 = Table("group_detail_info_ver1", columns={
    "60001": Column("group_code"),
    "60002": Column("owner_uid"),
    "60004": Column("create_time"),
    "60005": Column("max_member_count"),
    "60006": Column("member_count"),
    "60007": Column("group_name"),
    "60026": Column("remark"),
    "60216": Column("pinned_announce"),
    "60217": Column("description"),
    "60218": Column("labels"),
    "60224": Column("entrance_q"),
    "60340": Column("leave_flag", enum=LEAVE_FLAGS),
    "60241": Column("custom_labels", proto={
        60001: ProtoField("group_code"),
        60121: ProtoField("setter_uid"),
        60122: ProtoField("label_id"),
        60123: ProtoField("set_time"),
        60127: ProtoField("content"),
    }),
    "60242": Column("address", proto={
        60131: ProtoField("setter_uid"),
        60132: ProtoField("set_time"),
        60133: ProtoField("location_id"),
        60134: ProtoField("longitude"),
        60135: ProtoField("latitude"),
        60136: ProtoField("location_name"),
    }),
})

group_ext_list = Table("group_ext_list", columns={
    "60001": Column("group_code"),
    "66720": Column("activity_score"),
    "66726": Column("period_msg_count"),
    "66723": Column("lucky_char_content"),
    "66732": Column("owner", proto={
        60002: ProtoField("owner_uid"),
        66530: ProtoField("owner_uin"),
    }),
})

group_member3 = Table("group_member3", columns={
    "60001": Column("group_code"),
    "1000": Column("uid"),
    "1002": Column("uin"),
    "20002": Column("nickname"),
    "64003": Column("card"),
    "64007": Column("join_time"),
    "64008": Column("last_speak_time"),
    "64009": Column("mute_until"),
    "64010": Column("admin_flag", enum=ADMIN_FLAGS),
    "64016": Column("member_flag", enum=LEAVE_FLAGS),
    "64023": Column("custom_title"),
    "64035": Column("member_level"),
})

group_member_level_info = Table("group_member_level_info", columns={
    "60001": Column("group_code"),
    "67103": Column("levels", proto={
        67200: ProtoField("level"),
        67201: ProtoField("level_name"),
    }),
})

# 64205 之下的正文依次为 detail(64202) -> contentContainer(64227) -> items(64242, repeated)
# -> textContent(64452)。最后两层在同一列内重复出现，不在 Table 中登记，展开见 api/group_info.py
BULLETIN_DETAIL = {
    64221: ProtoField("publisher_uid"),
    64223: ProtoField("fid"),
    64225: ProtoField("published_time"),
    64226: ProtoField("updated_time"),
}

BULLETIN_ITEM = {
    64451: ProtoField("type"),  # 10 是「群公告」这类标题，不属于正文
    64452: ProtoField("text"),
}

group_bulletin = Table("group_bulletin", columns={
    "60001": Column("group_code"),
    "64205": Column("content"),
})

group_essence = Table("group_essence", columns={
    "60001": Column("group_code"),
    "67501": Column("msg_seq"),
    "67502": Column("msg_random"),
    "67503": Column("sender_uin"),
    "67504": Column("sender_nickname"),
    "67505": Column("set_status", enum=ESSENCE_STATES),
    "67506": Column("operator_uin"),
    "67507": Column("operator_nickname"),
    "67508": Column("set_time"),
})

group_notify_list = Table("group_notify_list", columns={
    "61001": Column("created_time"),
    "61002": Column("event", enum=NOTIFY_EVENTS),
    "61003": Column("state", enum=NOTIFY_STATES),
    "61004": Column("group", proto={
        60001: ProtoField("group_code"),
        60007: ProtoField("group_name"),
    }),
    "61005": Column("operated_member", proto={
        1000: ProtoField("uid"),
        20002: ProtoField("nickname"),
    }),
    "61007": Column("operator_member", proto={
        1000: ProtoField("uid"),
        20002: ProtoField("nickname"),
    }),
    "61008": Column("operate_time"),
    "61010": Column("remark"),
    "61011": Column("system_remark"),
})
