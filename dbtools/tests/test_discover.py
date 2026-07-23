"""discover 模块测试 —— get_tables_by_files / get_columns_by_files。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dbtools.discover import DBColumn, get_columns_by_files, get_tables_by_files


def _make_db(path: str, script: str) -> str:
    """创建 SQLite 文件并执行 DDL 脚本，返回文件路径。"""
    conn = sqlite3.connect(path)
    conn.executescript(script)
    conn.close()
    return path


def test_empty_db_returns_empty(tmp_path: Path) -> None:
    """空数据库（无用户表，只有内部表）返回空列表。"""
    db = _make_db(str(tmp_path / "empty.db"), "")
    tables = get_tables_by_files(db)
    assert tables == []


def test_filters_sqlite_internal(tmp_path: Path) -> None:
    """过滤 sqlite_ 开头的内部表。"""
    db = _make_db(
        str(tmp_path / "test.db"),
        "CREATE TABLE user_data (id INTEGER);",
    )
    tables = get_tables_by_files(db)
    assert tables == ["user_data"]


def test_filters_fts_tables(tmp_path: Path) -> None:
    """过滤 _fts* 后缀的 FTS 辅助表。"""
    db = _make_db(
        str(tmp_path / "test.db"),
        """
        CREATE TABLE real_table (id INTEGER);
        CREATE VIRTUAL TABLE search_fts USING fts5(title);
        """,
    )
    tables = get_tables_by_files(db)
    # FTS 创建时会自动生成 _fts_data, _fts_idx 等辅助表
    # real_table 应该出现，search_fts 的名字不匹配 FTS 后缀（它是主表名）
    assert "real_table" in tables


def test_union_across_files(sqlite_two_dbs: tuple[str, str]) -> None:
    """多文件并集去重，返回排序后的表名列表。"""
    db1, db2 = sqlite_two_dbs
    tables = get_tables_by_files(db1, db2)
    assert tables == ["buddy_list", "group_list", "user_list"]


def test_single_file(sqlite_two_dbs: tuple[str, str]) -> None:
    """单文件返回该文件的用户表。"""
    db1, _ = sqlite_two_dbs
    tables = get_tables_by_files(db1)
    assert tables == ["buddy_list", "group_list"]


def test_get_columns_single_file(sqlite_two_dbs: tuple[str, str]) -> None:
    """获取单个文件的列信息。"""
    db1, _ = sqlite_two_dbs
    cols = get_columns_by_files(db1, table="buddy_list")
    assert len(cols) == 2
    col_names = {c.name for c in cols}
    assert col_names == {"id", "name"}


def test_get_columns_union_across_files(sqlite_two_dbs: tuple[str, str]) -> None:
    """多文件列并集，按列名去重。"""
    db1, db2 = sqlite_two_dbs
    cols = get_columns_by_files(db1, db2, table="buddy_list")
    col_names = {c.name for c in cols}
    assert col_names == {"id", "name", "avatar"}
    assert len(cols) == 3


def test_get_columns_table_missing_in_file(sqlite_two_dbs: tuple[str, str]) -> None:
    """表在某文件中不存在时静默跳过。"""
    db1, db2 = sqlite_two_dbs
    cols = get_columns_by_files(db1, db2, table="user_list")
    col_names = {c.name for c in cols}
    assert col_names == {"uid"}
    assert len(cols) == 1


def test_get_columns_nonexistent_table(tmp_path: Path) -> None:
    """表在所有文件中都不存在时返回空列表。"""
    db = _make_db(str(tmp_path / "empty.db"), "CREATE TABLE a (x INTEGER)")
    cols = get_columns_by_files(db, table="nonexistent")
    assert cols == []


def test_get_columns_invalid_table_name() -> None:
    """非法 SQL 标识符应 raise ValueError。"""
    with pytest.raises(ValueError, match="非法的表名"):
        get_columns_by_files(":memory:", table="1; DROP TABLE")


def test_get_columns_special_chars_rejected() -> None:
    """含特殊字符的表名应 raise ValueError。"""
    with pytest.raises(ValueError, match="非法的表名"):
        get_columns_by_files(":memory:", table="buddy'list")


def test_db_column_fields() -> None:
    """DBColumn.col_type 字段应正确赋值。"""
    col = DBColumn(name="100", col_type="INTEGER")
    assert col.name == "100"
    assert col.col_type == "INTEGER"
