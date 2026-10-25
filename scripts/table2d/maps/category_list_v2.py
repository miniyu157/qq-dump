from . import Column, ProtoField, Status, Table

# 未明确语义的条目不用标 Status.DISCARDED：默认就不渲染未定义条目。
# 显式标记的条目里，DISCARDED 表示语义已明确但不再关心，
# HIDDEN 表示语义已明确但默认隐藏。


category_list_v2 = Table("category_list_v2", columns={
    "1000": Column("主人UID"),
    "25011": Column("分组对象",
        proto={
            25007: ProtoField("分组ID"),  # 0 表示默认分组
            25008: ProtoField("分组名称"),
            25009: ProtoField("排序序号", status=Status.DISCARDED),
            25010: ProtoField("分组成员数量"),
        },
    ),
    "25012": Column("数据更新时间", status=Status.HIDDEN),  # 毫秒时间戳
    "25018": Column("下次刷新时间", status=Status.HIDDEN),  # 约为 [25012] + 5 小时
    "20075": Column("上次更新时间", status=Status.HIDDEN),  # 毫秒时间戳，恒早于 [25012]
})
