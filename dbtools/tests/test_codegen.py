"""codegen 模块测试 —— add_db / add_columns / helpers。"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from dbtools.codegen.core import (
    _collect_column_ids,
    _extract_table_map_from_module,
    _get_existing_table_map,
    add_columns,
    add_db,
    add_empty_db,
    add_empty_table,
)


def _write_schema_files(root: Path) -> None:
    """创建最小 schema 目录结构（用于 monkeypatch _SCHEMA_DIR）。"""
    (root / "__init__.py").write_text(
        '"""schema 根模块。"""\n'
        "from __future__ import annotations\n"
        "from .base import Database\n"
        "\n"
        "__all_db__ = []\n"
        "__all__ = __all_db__\n",
        encoding="utf-8",
    )
    (root / "base.py").write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Column:\n"
        "    id: str\n"
        "    name: str\n"
        "    field_type: str = ''\n"
        "\n"
        "@dataclass\n"
        "class Table:\n"
        "    name: str\n"
        "    columns: list[Column]\n"
        "\n"
        "@dataclass\n"
        "class Database:\n"
        "    filename: str\n"
        "    tables: list[Table]\n",
        encoding="utf-8",
    )


# _extract_table_map_from_module


def test_extract_table_map_single() -> None:
    """单表模块返回正确的 {name: varname} 映射。"""
    source = "from ..base import Column, Table\nBUDDY_LIST = Table(name='buddy_list', columns=[])\n"
    mod = ast.parse(source)
    result = _extract_table_map_from_module(mod)
    assert result == {"buddy_list": "BUDDY_LIST"}


def test_extract_table_map_multi() -> None:
    """多表模块返回所有表的映射（P0 回归测试）。"""
    source = (
        "from ..base import Table\n"
        "AI_AVATAR = Table(name='ai_avatar', columns=[])\n"
        "USER_TAB_TABLE = Table(name='user_tab_table', columns=[])\n"
        "USER_SEC_QUALITY_TABLE = Table(name='user_sec_quality_table', columns=[])\n"
    )
    mod = ast.parse(source)
    result = _extract_table_map_from_module(mod)
    assert result == {
        "ai_avatar": "AI_AVATAR",
        "user_tab_table": "USER_TAB_TABLE",
        "user_sec_quality_table": "USER_SEC_QUALITY_TABLE",
    }


def test_extract_table_map_empty() -> None:
    """无 Table 定义的模块返回空 dict。"""
    source = "x = 1\n"
    mod = ast.parse(source)
    result = _extract_table_map_from_module(mod)
    assert result == {}


# _collect_column_ids (P4 回归)


def test_collect_column_ids_normal() -> None:
    """正常 Column 列表应返回正确的 id 集合。"""
    source = "[Column(id='0', name='a'), Column(id='1', name='b')]"
    expr = ast.parse(source, mode="eval")
    assert isinstance(expr.body, ast.List)
    assert _collect_column_ids(expr.body) == {"0", "1"}


def test_collect_column_ids_non_call_raises() -> None:
    """列表中包含非 Call 元素时应 raise ValueError。"""
    source = "[Column(id='0'), 'not_a_column']"
    expr = ast.parse(source, mode="eval")
    assert isinstance(expr.body, ast.List)
    with pytest.raises(ValueError, match=r"columns\[1\]"):
        _collect_column_ids(expr.body)


def test_collect_column_ids_wrong_call_raises() -> None:
    """列表中包含非 Column 调用时应 raise ValueError。"""
    source = "[Column(id='0'), Table(name='x', columns=[])]"
    expr = ast.parse(source, mode="eval")
    assert isinstance(expr.body, ast.List)
    with pytest.raises(ValueError, match=r"columns\[1\]"):
        _collect_column_ids(expr.body)


def test_collect_column_ids_empty_list() -> None:
    """空列表返回空集合。"""
    expr = ast.parse("[]", mode="eval")
    assert isinstance(expr.body, ast.List)
    assert _collect_column_ids(expr.body) == set()


# add_db / add_empty_db / add_empty_table


def test_add_db_creates_new(tmp_path: Path) -> None:
    """add_db 创建新数据库子包。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("new_db.db", ["buddy_list"])

    assert (tmp_path / "new_db").is_dir()
    assert (tmp_path / "new_db" / "__init__.py").exists()
    assert (tmp_path / "new_db" / "buddy_list.py").exists()

    # 验证 __init__.py 包含正确的 Database 调用
    init_content = (tmp_path / "new_db" / "__init__.py").read_text()
    assert "filename='new_db.db'" in init_content


def test_add_db_merges_existing(tmp_path: Path) -> None:
    """add_db 增量合并已有数据库，不移除现有表。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        add_db("test.db", ["group_list"])

    assert (tmp_path / "test" / "buddy_list.py").exists()
    assert (tmp_path / "test" / "group_list.py").exists()

    # buddy_list 不应被重复添加
    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert init_content.count("BUDDY_LIST") == 2  # 一次 import，一次在 tables 列表


def test_add_db_duplicate_table_noop(tmp_path: Path) -> None:
    """重复添加已有表不产生副作用。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        before = (tmp_path / "test" / "__init__.py").read_text()
        add_db("test.db", ["buddy_list"])
        after = (tmp_path / "test" / "__init__.py").read_text()

    assert before == after


def test_add_db_invalid_filename() -> None:
    """非法文件名应 raise ValueError。"""
    with pytest.raises(ValueError, match="必须以 .db 结尾"):
        add_db("no_extension", ["buddy_list"])


def test_add_db_non_identifier_dirname() -> None:
    """去掉 .db 后不是合法 Python 标识符应 raise ValueError。"""
    with pytest.raises(ValueError, match="不是合法的 Python 标识符"):
        add_db("123-invalid.db", ["buddy_list"])


def test_add_empty_db(tmp_path: Path) -> None:
    """add_empty_db 创建空数据库。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_empty_db("empty.db")

    assert (tmp_path / "empty").is_dir()
    assert (tmp_path / "empty" / "__init__.py").exists()


def test_add_empty_db_idempotent(tmp_path: Path) -> None:
    """add_empty_db 重复调用不产生副作用。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_empty_db("idem.db")
        before = (tmp_path / "idem" / "__init__.py").read_text()
        add_empty_db("idem.db")
        after = (tmp_path / "idem" / "__init__.py").read_text()
    assert before == after


def test_add_empty_table_new_db(tmp_path: Path) -> None:
    """add_empty_table 在数据库不存在时自动创建。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_empty_table("auto.db", "empty_table")

    assert (tmp_path / "auto").is_dir()
    assert (tmp_path / "auto" / "empty_table.py").exists()


def test_add_empty_table_existing_db(tmp_path: Path) -> None:
    """add_empty_table 向已有数据库追加空表。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        add_empty_table("test.db", "new_empty")

    assert (tmp_path / "test" / "new_empty.py").exists()
    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert "NEW_EMPTY" in init_content


def test_add_empty_table_idempotent(tmp_path: Path) -> None:
    """add_empty_table 重复调用不产生副作用。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_empty_table("test.db", "once")
        before = (tmp_path / "test" / "once.py").read_text()
        add_empty_table("test.db", "once")
        after = (tmp_path / "test" / "once.py").read_text()
    assert before == after


# _get_existing_table_map (P0 回归)


def test_get_existing_table_map_single_module(tmp_path: Path) -> None:
    """单表模块应正确返回 {name: varname}。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    result = _get_existing_table_map(tmp_path / "test")
    assert result == {"buddy_list": "BUDDY_LIST"}


def test_get_existing_table_map_multi_module(tmp_path: Path) -> None:
    """多表模块应返回所有表的映射（P0 核心回归测试）。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    # 手动添加多表模块 config.py
    (test_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "AI_AVATAR = Table(name='ai_avatar', columns=[])\n"
        "USER_TAB_TABLE = Table(name='user_tab_table', columns=[])\n"
        "USER_SEC_QUALITY_TABLE = Table(name='user_sec_quality_table', columns=[])\n",
        encoding="utf-8",
    )
    # 更新 __init__.py，添加 config 导入
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .config import AI_AVATAR, USER_TAB_TABLE, USER_SEC_QUALITY_TABLE",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, AI_AVATAR, USER_TAB_TABLE, USER_SEC_QUALITY_TABLE]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    result = _get_existing_table_map(test_dir)
    assert result == {
        "buddy_list": "BUDDY_LIST",
        "ai_avatar": "AI_AVATAR",
        "user_tab_table": "USER_TAB_TABLE",
        "user_sec_quality_table": "USER_SEC_QUALITY_TABLE",
    }


# add_columns


def test_add_columns_appends_new(tmp_path: Path) -> None:
    """add_columns 追加新列到已有表。"""
    _write_schema_files(tmp_path)
    db_path = tmp_path / "test_db.db"

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE buddy_list (col_a INTEGER, col_b TEXT)")
    conn.close()

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test_db.db", ["buddy_list"])
        add_columns("test_db.db", "buddy_list", str(db_path))

    buddy_content = (tmp_path / "test_db" / "buddy_list.py").read_text()
    assert "col_a" in buddy_content
    assert "col_b" in buddy_content


def test_add_columns_idempotent(tmp_path: Path) -> None:
    """add_columns 重复调用不产生重复列。"""
    _write_schema_files(tmp_path)
    db_path = tmp_path / "test_db.db"

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE buddy_list (col_a INTEGER)")
    conn.close()

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test_db.db", ["buddy_list"])
        add_columns("test_db.db", "buddy_list", str(db_path))
        before = (tmp_path / "test_db" / "buddy_list.py").read_text()
        add_columns("test_db.db", "buddy_list", str(db_path))
        after = (tmp_path / "test_db" / "buddy_list.py").read_text()

    assert before == after


def test_add_columns_nonexistent_db(tmp_path: Path) -> None:
    """数据库不存在时 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        with pytest.raises(ValueError, match="not found in schema"):
            add_columns("no_such.db", "buddy_list", ":memory:")


def test_add_columns_nonexistent_table(tmp_path: Path) -> None:
    """表不存在时 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        with pytest.raises(ValueError, match="not found"):
            add_columns("test.db", "no_such_table", ":memory:")


def test_add_columns_skips_utility_modules(tmp_path: Path) -> None:
    """P1 回归：add_columns 不扫描 __init__.py 未导入的模块。

    在 db 目录下创建一个有语法错误的 _util.py，
    add_columns 应该不受影响地正常工作。
    """
    _write_schema_files(tmp_path)
    db_path = tmp_path / "test_db.db"

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE buddy_list (col_a INTEGER)")
    conn.close()

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test_db.db", ["buddy_list"])
        # 添加一个未导入、有语法错误的工具模块
        (tmp_path / "test_db" / "_util.py").write_text("this is not valid python {{{")
        # 不应崩溃
        add_columns("test_db.db", "buddy_list", str(db_path))

    buddy_content = (tmp_path / "test_db" / "buddy_list.py").read_text()
    assert "col_a" in buddy_content
