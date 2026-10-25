import os

from .buddy_list import buddy_list
from .c2c_msg_table import c2c_msg_table
from .category_list_v2 import category_list_v2
from .group_msg_fts import group_msg_fts
from .profile_info_adelie import profile_info_adelie
from .profile_info_v6 import profile_info_v6

DATABASES = {
    "group_msg_fts.db": {
        "group_msg_fts": group_msg_fts,
    },
    "profile_info.db": {
        "buddy_list": buddy_list,
        "category_list_v2": category_list_v2,
        "profile_info_adelie": profile_info_adelie,
        "profile_info_v6": profile_info_v6,
    },
    "nt_msg.db": {
        "c2c_msg_table": c2c_msg_table,
    },
}


def for_file(db_path, table_name):
    """库文件名以 DATABASES 的键结尾即算命中，再取其中的表；未命中返回 None"""
    base = os.path.basename(db_path)
    for name, tables in DATABASES.items():
        if base.endswith(name):
            return tables.get(table_name)
    return None
