"""buddy_list, buddy_req_list_5 —— 好友列表与好友请求。"""

from __future__ import annotations

from ..base import Column, Table

BUDDY_LIST = Table(
    name="buddy_list",  # 好友列表
    columns=[
        Column(id="1000", name="uid", field_type="TEXT"),  # 好友 uid，形如 "u_xxxxxxxxxxxxxxxxxx"
        Column(id="1001", name="qid", field_type="TEXT"),  # 好友 QID / 自定义 QQ 用户名，未设置时为空
        Column(id="1002", name="uin", field_type="INTEGER"),  # 好友 QQ 号
        Column(
            id="25007", name="group_id", field_type="INTEGER?"
        ),  # 所属分组 ID，NULL 表示默认分组（category_list_v2 中 group_id=0 的"我的好友"）
    ],
)
