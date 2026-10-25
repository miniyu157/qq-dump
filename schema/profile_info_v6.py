from . import Column, ProtoField, Table

# 密友关系 ID 随版本增补，未收录的 ID 不映射名称
CLOSE_RELATIONS = {
    1: "情侣",
    2: "闺蜜",
    3: "基友",
    26: "死党",
    81: "学习搭子",
    82: "运动搭子",
    101: "饭搭子",
}

profile_info_v6 = Table("profile_info_v6", columns={
    "1000": Column("uid"),
    "1001": Column("qid"),  # 未设置时为 NULL
    "1002": Column("uin"),
    "20001": Column("deletion_time"),  # 非好友行可作删除时间，好友行的值实为资料同步批次时间戳
    "20002": Column("nickname"),
    "20006": Column("birth_year"),  # 未设置时为 0
    "20007": Column("birth_month"),  # 1~12，未设置为 0
    "20008": Column("birth_day"),  # 1~31，未设置为 0
    "20009": Column("remark"),
    "20011": Column("signature"),
    "20014": Column("gender", enum={0: "未知", 1: "男", 2: "女", 255: "秘密"}),
    "20048": Column("group_id"),
    "20070": Column("intimacy"),  # 非好友或未产生亲密度时为 0
    "20072": Column("close_relation", proto={
        20073: ProtoField("preset_relation_ids", enum=CLOSE_RELATIONS),
        20074: ProtoField("current_relation_id", enum=CLOSE_RELATIONS),
    }),
    "24103": Column("age"),  # QQ 根据生日推算
})
