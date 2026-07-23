"""数据库发现结果类型 —— 从 SQLite 文件中读到的原始事实。

这些 dataclass 仅描述表的物理结构，不包含业务含义。
与 schema 层的声明式结构互为镜像，但这里绝对中立、不含标注。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DBColumn:
    """从 SQLite PRAGMA table_info 发现的列元数据。

    name: SQLite 列名
    col_type: SQL 类型声明（INTEGER, TEXT, BLOB 等）
    """

    name: str
    col_type: str


@dataclass
class DBTable:
    """从 SQLite 文件发现的一张表。

    name: SQLite 表名
    columns: DBColumn 数组
    """

    name: str
    columns: list[DBColumn]


@dataclass
class DBFile:
    """一个 SQLite 数据库文件结构。

    filename: SQLite 数据库应该的文件名称，带 .db 后缀
    tables: DBTable 数组
    """

    filename: str
    tables: list[DBTable]
