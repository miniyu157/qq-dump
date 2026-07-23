"""为 discover 和 codegen 测试提供共用 fixtures。

discover 测试使用临时文件 SQLite 数据库，codegen 测试使用
临时目录模拟 dbtools/schema/ 结构并通过 monkeypatch 注入。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_two_dbs(tmp_path: Path) -> tuple[str, str]:
    """创建两个 SQLite 文件，含不同表结构。

    db1 有 buddy_list (id, name) 和 group_list (id)
    db2 有 buddy_list (id, name, avatar) 和 user_list (uid)
    """
    db1 = str(tmp_path / "db1.db")
    db2 = str(tmp_path / "db2.db")

    conn1 = sqlite3.connect(db1)
    conn1.executescript(
        """
        CREATE TABLE buddy_list (id INTEGER, name TEXT);
        CREATE TABLE group_list (id INTEGER);
        """
    )
    conn1.close()

    conn2 = sqlite3.connect(db2)
    conn2.executescript(
        """
        CREATE TABLE buddy_list (id INTEGER, name TEXT, avatar BLOB);
        CREATE TABLE user_list (uid INTEGER);
        """
    )
    conn2.close()

    return db1, db2
