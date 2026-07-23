"""profile_info_v6 —— 用户资料缓存（核心表）。"""

from __future__ import annotations

from ..base import Column, EnumType, EnumValue, ProtoField, ProtoStruct, Table

PROFILE_INFO_V6 = Table(
    name="profile_info_v6",  # 用户资料贮藏
    columns=[
        # ── 基础标识（高覆盖率，99%+） ──
        Column(id="1000", name="uid", field_type="TEXT"),  # 用户 uid（主键），形如 "u_xxx"
        Column(id="1001", name="qid", field_type="TEXT"),  # 自定义 QQ 用户名（QID），未设置时为空
        Column(id="1002", name="uin", field_type="INTEGER"),  # QQ 号
        Column(id="20002", name="nickname", field_type="TEXT"),  # 昵称
        # ── 详细资料（~17% 覆盖率，仅浏览过资料卡的用户才有） ──
        Column(id="20001", name="unknown_20001_ts", field_type="INTEGER"),  # 毫秒时间戳
        Column(id="20003", name="unknown_20003_ts", field_type="INTEGER"),  # 毫秒时间戳，多为缓存写入时间
        Column(id="20004", name="avatar_url", field_type="TEXT"),  # 头像 URL
        Column(id="20005", name="unknown_20005_ts", field_type="INTEGER"),  # 毫秒时间戳，疑似头像/生日设置时间
        Column(id="20006", name="birthday_year", field_type="INTEGER"),  # 生日-年，0=未设置
        Column(id="20007", name="birthday_month", field_type="INTEGER"),  # 生日-月
        Column(id="20008", name="birthday_day", field_type="INTEGER"),  # 生日-日
        Column(id="20009", name="alias", field_type="TEXT"),  # 主人设置的别名（备注）
        Column(id="20010", name="unknown_20010_ts", field_type="INTEGER"),  # 毫秒时间戳
        Column(id="20011", name="signature", field_type="TEXT"),  # 个性签名
        Column(id="20012", name="unknown_20012_ts", field_type="INTEGER"),  # 毫秒时间戳
        Column(
            id="20014",
            name="gender",
            field_type="INTEGER",
            enum=EnumType(
                name="Gender",
                values=[
                    EnumValue(number=0, label="unset", description="未设置"),
                    EnumValue(number=1, label="male", description="男"),
                    EnumValue(number=2, label="female", description="女"),
                    EnumValue(number=255, label="private", description="未公开"),
                ],
            ),
        ),
        Column(id="20016", name="unknown_20016_ts", field_type="INTEGER"),  # 秒级时间戳
        Column(id="20017", name="unknown_20017", field_type="BLOB"),  # 始终为 NULL（可能已废弃）
        Column(id="24103", name="qq_level", field_type="INTEGER"),  # QQ 等级（0~120）
        Column(id="20042", name="unknown_20042", field_type="BLOB"),  # 始终为 NULL
        Column(id="20059", name="unknown_20059", field_type="BLOB"),  # 始终为 NULL
        Column(id="20060", name="unknown_20060", field_type="INTEGER"),  # 始终为 0
        Column(id="20061", name="unknown_20061", field_type="INTEGER"),  # 始终为 0
        Column(id="20043", name="unknown_20043", field_type="INTEGER"),  # 标志位，取值 0 或 60
        Column(id="20048", name="unknown_20048", field_type="INTEGER"),  # 小整数枚举 0~4
        Column(id="20037", name="unknown_20037", field_type="INTEGER"),  # 标志位，多为 0，偶见 10
        Column(id="20056", name="unknown_20056", field_type="INTEGER"),  # 标志位/位域，偶见 0x10000001
        Column(id="20067", name="unknown_20067_ts", field_type="INTEGER"),  # 秒级时间戳
        Column(id="20057", name="unknown_20057", field_type="BLOB"),  # 始终为 NULL
        Column(id="20070", name="unknown_20070", field_type="INTEGER"),  # 小整数，多为 0，少数 42~48
        Column(id="20071", name="unknown_20071", field_type="INTEGER"),  # 标志位，几乎全是 0
        Column(
            id="21000",
            name="profile_detail",  # protobuf：位置、等级、VIP 等扩展资料
            field_type="BLOB",
            proto=ProtoStruct(
                name="ProfileDetail",
                fields=[
                    ProtoField(number=22003, name="unknown_22003", field_type="string"),
                    ProtoField(
                        number=22004,
                        name="level_info",  # QQ 等级相关
                        field_type="nested",
                        struct=ProtoStruct(
                            name="LevelInfo",
                            fields=[
                                ProtoField(number=28001, name="unknown_28001", field_type="varint"),
                                ProtoField(number=28002, name="unknown_28002", field_type="varint"),
                                ProtoField(number=28003, name="unknown_28003", field_type="varint"),
                                ProtoField(number=28004, name="unknown_28004", field_type="varint"),
                                ProtoField(number=28007, name="unknown_28007", field_type="varint"),
                                ProtoField(number=28013, name="unknown_28013", field_type="varint"),
                                ProtoField(number=28014, name="unknown_28014", field_type="varint"),
                                ProtoField(number=28015, name="unknown_28015", field_type="varint"),
                                ProtoField(number=28018, name="unknown_28018", field_type="varint"),
                                ProtoField(number=28019, name="unknown_28019", field_type="varint"),
                                ProtoField(number=28027, name="unknown_28027", field_type="varint"),
                            ],
                        ),
                    ),
                    ProtoField(
                        number=22005,
                        name="location_info",  # 位置信息（国家/省份/城市）
                        field_type="nested",
                        struct=ProtoStruct(
                            name="LocationInfo",
                            fields=[
                                ProtoField(number=20018, name="unknown_20018", field_type="varint"),
                                ProtoField(number=20019, name="unknown_20019", field_type="varint"),
                                ProtoField(number=20021, name="unknown_20021", field_type="string"),
                                ProtoField(number=20022, name="unknown_20022", field_type="varint"),
                                ProtoField(number=20023, name="unknown_20023", field_type="string"),
                                ProtoField(number=20027, name="country", field_type="string"),
                                ProtoField(number=20028, name="province", field_type="string"),
                                ProtoField(number=20029, name="unknown_20029", field_type="string"),
                                ProtoField(number=20030, name="unknown_20030", field_type="string"),
                                ProtoField(number=20036, name="city", field_type="string"),
                                ProtoField(number=20038, name="unknown_20038_ts", field_type="varint"),
                            ],
                        ),
                    ),
                    ProtoField(
                        number=22006,
                        name="online_info",  # 在线状态 / 设备
                        field_type="nested",
                        struct=ProtoStruct(
                            name="OnlineInfo",
                            fields=[
                                ProtoField(number=20015, name="unknown_20015_ts", field_type="varint"),
                                ProtoField(number=20035, name="client_version", field_type="string"),
                                ProtoField(number=27003, name="unknown_27003", field_type="string"),
                                ProtoField(number=27006, name="unknown_27006_ts", field_type="varint"),
                                ProtoField(number=27013, name="unknown_27013", field_type="varint"),
                                ProtoField(number=27014, name="unknown_27014", field_type="varint"),
                            ],
                        ),
                    ),
                    ProtoField(
                        number=22007,
                        name="privacy_info",  # 隐私/安全设置
                        field_type="nested",
                        struct=ProtoStruct(
                            name="PrivacyInfo",
                            fields=[
                                ProtoField(number=20044, name="unknown_20044", field_type="varint"),
                                ProtoField(number=20045, name="unknown_20045", field_type="varint"),
                                ProtoField(number=20049, name="unknown_20049", field_type="varint"),
                                ProtoField(number=29002, name="unknown_29002", field_type="varint"),
                            ],
                        ),
                    ),
                    ProtoField(
                        number=22008,
                        name="vip_info",  # VIP 会员 / 个性化装扮
                        field_type="nested",
                        struct=ProtoStruct(
                            name="VipInfo",
                            fields=[
                                ProtoField(number=30002, name="unknown_30002_ts", field_type="varint"),
                                ProtoField(number=30010, name="vip_json", field_type="string"),
                                ProtoField(number=30012, name="vip_config_json", field_type="string"),
                                ProtoField(number=30016, name="unknown_30016", field_type="varint"),
                                ProtoField(number=30017, name="unknown_30017_ts", field_type="varint"),
                                ProtoField(number=30018, name="unknown_30018_ts", field_type="varint"),
                                ProtoField(number=30021, name="unknown_30021_ts", field_type="varint"),
                            ],
                        ),
                    ),
                ],
            ),
        ),
        Column(
            id="20072", name="contact_flag", field_type="BLOB"
        ),  # 关联标志位（4 字节 LE uint32 bitmask，恒值 0x9E6C2，偶见 8 字节变体）。好友 100% 持有，也存在于交互过的非好友。非关联用户为 NULL。
        Column(id="20075", name="unknown_20075", field_type="INTEGER"),  # 多为 0，偶见大整数（可能是来源 UIN）
        Column(id="20066", name="unknown_20066", field_type="BLOB"),  # 始终为 NULL
        Column(id="24104", name="unknown_24104_ts", field_type="INTEGER"),  # 秒级时间戳
        Column(id="24105", name="unknown_24105", field_type="BLOB"),  # protobuf 包裹的文本（镜像 signature）
        Column(id="24106", name="unknown_24106", field_type="TEXT"),  # FTS 索引列，始终为空字符串
        Column(id="24107", name="unknown_24107", field_type="TEXT"),  # FTS 索引列，始终为空字符串
        Column(id="24108", name="unknown_24108", field_type="TEXT"),  # FTS 索引列，始终为空字符串
        Column(id="24109", name="unknown_24109", field_type="TEXT"),  # FTS 索引列，始终为空字符串
        Column(id="24110", name="unknown_24110", field_type="INTEGER"),  # 标志位，几乎全是 0
        Column(id="24111", name="unknown_24111_ts", field_type="INTEGER"),  # 秒级时间戳
        Column(id="20083", name="unknown_20083", field_type="INTEGER"),  # 小整数，多为 0
    ],
)

GENDER_MAP: dict[int, str] = {v.number: v.label for v in PROFILE_INFO_V6.column("gender").enum.values}
