"""数据库连接与映射解析的底层封装。"""

import sqlite3

from schema import Table
from schema.databases import for_file


def open_db(path: str) -> sqlite3.Connection:
    """以只读模式打开数据库，调用方负责关闭"""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def table_map(db_path: str, table: str) -> Table:
    """按库文件名与表名取映射，未登记抛 KeyError"""
    mapping = for_file(db_path, table)
    if mapping is None:
        raise KeyError(f"未登记的映射: {table}")
    return mapping


def resolve_column(table: Table, name: str) -> str:
    """语义名称对应的列号，未登记抛 KeyError"""
    column = table.column_id(name)
    if column is None:
        raise KeyError(f"未登记的列: {name}")
    return column


def resolve_field(table: Table, column: str, name: str) -> int:
    """列下 protobuf 字段名称对应的字段号，未登记抛 KeyError"""
    field = table.field_id(column, name)
    if field is None:
        raise KeyError(f"未登记的字段: {name}")
    return field
