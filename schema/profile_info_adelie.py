from . import Column, Table

# 机器人账号表，uid 可与 profile_info_v6、buddy_list 关联
profile_info_adelie = Table("profile_info_adelie", columns={
    "1000": Column("uid"),
})
