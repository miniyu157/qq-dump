from . import Column, ProtoField, Status, Table

RELATIONS = {
    1: "情侣",
    2: "闺蜜",
    3: "基友",
    26: "死党",
    81: "学习搭子",
    82: "运动搭子",
    101: "饭搭子",
}

profile_info_v6 = Table("profile_info_v6", columns={
    "1001": Column("Qid"),  # 未设置则为 NULL
    "1002": Column("Uin"),
    "20001": Column("根据时间戳判断好友/非好友", status=Status.EXPLORING),  # 包含所有好友、曾经的好友；取值可分为多个层级的毫秒时间戳
    "20002": Column("昵称"),
    "20003": Column("时间戳疑似与群聊相关", status=Status.EXPLORING),
    "20009": Column("主人设置的备注"),
    "20011": Column("个性签名"),
    "1000": Column("Uid"),
    "20004": Column("头像链接", status=Status.DISCARDED),
    "20006": Column("出生年"),  # 未设置时为 0
    "20007": Column("出生月"),  # 1~12，未设置为 0
    "20008": Column("出生日"),  # 1~31，未设置为 0
    "20014": Column("性别", enum={0: "未知", 1: "男", 2: "女", 255: "秘密"}),
    "20048": Column("好友/非好友分组 ID", status=Status.EXPLORING),
    "20070": Column("亲密度"),  # 与该好友的亲密度数值，非好友或未产生亲密度时为 0
    # 密友关系 ID 随版本增补，未收录的 ID 不映射名称
    "20072": Column("密友关系", status=Status.HIDDEN, proto={
        20073: ProtoField("预设关系 ID 列表", enum=RELATIONS),
        20074: ProtoField("当前展示关系 ID", enum=RELATIONS),
    }),
    "21000": Column("尊贵身份标识符", status=Status.DISCARDED),
    "24103": Column("年龄"),  # QQ 根据生日推算的年龄
    "24104": Column("个性签名更新时间"),  # 秒级时间戳
    "24105": Column("个性签名校验值", status=Status.DISCARDED),
})
