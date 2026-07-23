"""dbtools —— QQNT 数据库解析工具。

公开 API:
    from dbtools import (
        AccountInfo,        # 用户账号信息
        DBColumn,           # 数据库列元数据（发现层）
        DBFile,             # 数据库文件结构（发现层）
        DBTable,            # 数据库表结构（发现层）
        FriendGroup,        # 好友分组
        get_by_uid,         # 按 UID 查询用户
        get_my_info,        # 查询主人账号
        list_groups,        # 好友分组列表
        get_tables_by_files,    # 从数据库文件发现所有表
        get_columns_by_files,   # 从数据库文件发现指定表的列
    )
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf")

from .discover import DBColumn, DBFile, DBTable, get_columns_by_files, get_tables_by_files  # noqa: E402
from .groups import list_groups  # noqa: E402
from .info import get_by_uid, get_my_info  # noqa: E402
from .types import AccountInfo, FriendGroup  # noqa: E402

__all__ = [
    "AccountInfo",
    "DBColumn",
    "DBFile",
    "DBTable",
    "FriendGroup",
    "get_by_uid",
    "get_my_info",
    "get_columns_by_files",
    "get_tables_by_files",
    "list_groups",
]
