"""QQNT 数据库 schema —— 公开 API。

用法：
    from dbtools.schema import PROFILE_INFO_DB, Column, Table, ProtoField, ProtoStruct, Database
"""

from __future__ import annotations
import warnings
from .base import Database, EnumType, EnumValue, Column, FlagBit, FlagsType, ProtoField, ProtoStruct, Table
from .profile_info import PROFILE_INFO_DB
from .nt_msg import NT_MSG_DB

warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf")
__all_db__ = ["PROFILE_INFO_DB", "NT_MSG_DB"]
__all_base__ = [
    "Column",
    "Database",
    "EnumType",
    "EnumValue",
    "FlagBit",
    "FlagsType",
    "ProtoField",
    "ProtoStruct",
    "Table",
]
__all__ = __all_db__ + __all_base__
