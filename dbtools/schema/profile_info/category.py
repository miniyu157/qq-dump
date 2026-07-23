"""category_list_v2, category_list —— 好友分组列表。"""

from __future__ import annotations
from ..base import Column, ProtoField, ProtoStruct, Table

CATEGORY_LIST_V2 = Table(
    name="category_list_v2",  # 分组列表，一般只有一行
    columns=[
        Column(id="1000", name="owner_uid", field_type="TEXT"),  # 主人 UID
        Column(id="25006", name="unknown_25006", field_type="INTEGER"),  # 未知，示例值 2266
        Column(id="25013", name="unknown_25013", field_type="INTEGER"),  # 未知，示例值 843
        Column(id="25012", name="unknown_25012", field_type="INTEGER"),  # 未知，毫秒时间戳
        Column(id="20075", name="unknown_20075", field_type="INTEGER"),  # 未知，毫秒时间戳
        Column(id="25001", name="unknown_25001", field_type="BLOB"),  # 未知，示例值 NULL
        Column(
            id="25011",
            name="group_info",  # protobuf 分组信息，repeated
            field_type="BLOB",
            proto=ProtoStruct(
                name="GroupInfo",
                fields=[
                    ProtoField(number=25007, name="group_id", field_type="varint"),  # 分组 ID，0 为"我的好友"
                    ProtoField(number=25008, name="group_name", field_type="string"),  # 分组名称（UTF-8）
                    ProtoField(number=25009, name="sort_order", field_type="varint"),  # 排序序号
                    ProtoField(number=25010, name="member_count", field_type="varint"),  # 分组成员数
                ],
            ),
        ),
        Column(id="25015", name="unknown_25015", field_type="INTEGER"),  # 未知，示例值 1385308
        Column(id="25018", name="unknown_25018", field_type="INTEGER"),  # 未知，毫秒时间戳（旧版 DB 可能无此列）
    ],
)
