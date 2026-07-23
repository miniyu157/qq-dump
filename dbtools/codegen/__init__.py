"""codegen —— schema 代码生成与操作。

使用 ast 模块读取、生成、修改 dbtools/schema/ 下的 Python 源代码。

用法:
    from dbtools.codegen import add_columns, add_db, remove_db, remove_table
    from dbtools.discover import get_columns_by_files, get_tables_by_files

    tables = get_tables_by_files("path/to/db.db")
    add_db("my_db.db", tables)

    add_columns("my_db.db", "buddy_list", "path/to/db.db")
    remove_table("my_db.db", "buddy_list")
    remove_db("my_db.db")
"""

from __future__ import annotations

from .core import add_columns, add_db, add_empty_db, add_empty_table, remove_db, remove_table

__all__ = ["add_columns", "add_db", "add_empty_db", "add_empty_table", "remove_db", "remove_table"]
