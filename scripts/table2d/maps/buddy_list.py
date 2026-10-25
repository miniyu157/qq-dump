from . import Column, Table

buddy_list = Table("buddy_list", columns={
    "1000": Column("Uid"),
    "1001": Column("Qid"),
    "1002": Column("Uin"),
    "25007": Column("分组 ID"),  # NULL 表示默认分组 0
})
