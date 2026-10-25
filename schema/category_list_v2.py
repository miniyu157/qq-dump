from . import Column, ProtoField, Table

category_list_v2 = Table("category_list_v2", columns={
    "1000": Column("owner_uid"),
    "25011": Column("group", proto={
        25007: ProtoField("group_id"),  # 0 表示默认分组
        25008: ProtoField("group_name"),
    }),
})
