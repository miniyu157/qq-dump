"""profile_info.db —— 用户信息数据库。"""

from __future__ import annotations
from ..base import Database
from .profile import PROFILE_INFO_V6
from .category import CATEGORY_LIST_V2
from .buddy import BUDDY_LIST

PROFILE_INFO_DB = Database(
    filename="profile_info.db",
    tables=[
        PROFILE_INFO_V6,
        CATEGORY_LIST_V2,
        BUDDY_LIST,
    ],
)
