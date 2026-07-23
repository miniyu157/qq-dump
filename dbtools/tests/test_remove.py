"""codegen remove 操作测试 —— remove_db / remove_table。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from dbtools.codegen.core import (
    add_db,
    remove_db,
    remove_table,
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


# remove_db


def test_remove_db_deletes_directory(tmp_path: Path) -> None:
    """remove_db 删除子包目录和 __init__.py 中的引用。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    assert (tmp_path / "test").is_dir()

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_db("test.db")

    assert not (tmp_path / "test").exists()

    # schema/__init__.py 中不应再有引用
    init_content = (tmp_path / "__init__.py").read_text()
    assert "TEST_DB_DB" not in init_content
    assert "from .test import" not in init_content


def test_remove_db_nonexistent_raises(tmp_path: Path) -> None:
    """移除不存在的数据库 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        with pytest.raises(ValueError, match="not found"):
            remove_db("no_such.db")


def test_remove_db_invalid_filename() -> None:
    """非法文件名 raise ValueError。"""
    with pytest.raises(ValueError, match="必须以 .db 结尾"):
        remove_db("bad_name")


# remove_table — 单表模块


def test_remove_table_deletes_single_table_module(tmp_path: Path) -> None:
    """单表模块：删除 .py 文件和 __init__.py 中的引用。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list", "group_list"])

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "buddy_list")

    # buddy_list.py 应被删除
    assert not (tmp_path / "test" / "buddy_list.py").exists()
    # group_list.py 应保留
    assert (tmp_path / "test" / "group_list.py").exists()

    # __init__.py 中不再有 BUDDY_LIST
    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert "BUDDY_LIST" not in init_content
    assert "GROUP_LIST" in init_content


def test_remove_table_nonexistent_db_raises(tmp_path: Path) -> None:
    """数据库不存在时 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        with pytest.raises(ValueError, match="not found in schema"):
            remove_table("no_such.db", "buddy_list")


def test_remove_table_nonexistent_table_raises(tmp_path: Path) -> None:
    """表不存在时 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        with pytest.raises(ValueError, match="not found"):
            remove_table("test.db", "no_such_table")


def test_remove_last_table_leaves_empty_db(tmp_path: Path) -> None:
    """移除最后一张表后数据库子包保留（与 add_empty_db 对称）。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        remove_table("test.db", "buddy_list")

    assert (tmp_path / "test").is_dir()
    assert (tmp_path / "test" / "__init__.py").exists()
    assert not (tmp_path / "test" / "buddy_list.py").exists()

    # tables 列表应为空
    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert "tables=[]" in init_content


# remove_table — 多表模块


def test_remove_table_from_multi_table_module(tmp_path: Path) -> None:
    """多表模块：仅删除目标 Table 赋值，保留其他表。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    # 添加多表模块 config.py（2 张表）
    (test_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "TABLE_A = Table(name='table_a', columns=[])\n"
        "TABLE_B = Table(name='table_b', columns=[])\n",
        encoding="utf-8",
    )
    # 更新 __init__.py
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .config import TABLE_A, TABLE_B",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, TABLE_A, TABLE_B]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "table_a")

    # config.py 应保留（TABLE_B 还在）
    assert (test_dir / "config.py").exists()
    config_content = (test_dir / "config.py").read_text()
    assert "TABLE_B" in config_content
    assert "TABLE_A" not in config_content

    # __init__.py 中只应有 TABLE_B，不应有 TABLE_A
    init_after = (test_dir / "__init__.py").read_text()
    assert "TABLE_B" in init_after
    assert "TABLE_A" not in init_after
    assert "BUDDY_LIST" in init_after


def test_remove_last_table_from_multi_module_deletes_file(tmp_path: Path) -> None:
    """多表模块最后一个活跃表被移除时，删除整个模块文件。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    # 单表模块 config.py（只有一个活跃表）
    (test_dir / "extra.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "ONLY_TABLE = Table(name='only_table', columns=[])\n",
        encoding="utf-8",
    )
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .extra import ONLY_TABLE",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, ONLY_TABLE]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "only_table")

    assert not (test_dir / "extra.py").exists()
    init_after = (test_dir / "__init__.py").read_text()
    assert "ONLY_TABLE" not in init_after


def test_remove_table_idempotent_error(tmp_path: Path) -> None:
    """重复移除同一张表第二次应 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        remove_table("test.db", "buddy_list")
        with pytest.raises(ValueError, match="not found"):
            remove_table("test.db", "buddy_list")


# remove_table — 多表一次性移除


def test_remove_multiple_tables(tmp_path: Path) -> None:
    """一次移除多张独立的单表模块。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list", "group_list", "friend_list"])

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "buddy_list", "group_list")

    assert not (tmp_path / "test" / "buddy_list.py").exists()
    assert not (tmp_path / "test" / "group_list.py").exists()
    assert (tmp_path / "test" / "friend_list.py").exists()

    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert "BUDDY_LIST" not in init_content
    assert "GROUP_LIST" not in init_content
    assert "FRIEND_LIST" in init_content


def test_remove_multiple_from_same_multi_module(tmp_path: Path) -> None:
    """从同一个多表模块中移除多张表。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    (test_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "TABLE_A = Table(name='table_a', columns=[])\n"
        "TABLE_B = Table(name='table_b', columns=[])\n"
        "TABLE_C = Table(name='table_c', columns=[])\n",
        encoding="utf-8",
    )
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .config import TABLE_A, TABLE_B, TABLE_C",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, TABLE_A, TABLE_B, TABLE_C]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "table_a", "table_c")

    assert (test_dir / "config.py").exists()
    config_content = (test_dir / "config.py").read_text()
    assert "TABLE_B" in config_content
    assert "TABLE_A" not in config_content
    assert "TABLE_C" not in config_content

    init_after = (test_dir / "__init__.py").read_text()
    assert "TABLE_B" in init_after
    assert "TABLE_A" not in init_after
    assert "TABLE_C" not in init_after


def test_remove_all_from_multi_module_deletes_file(tmp_path: Path) -> None:
    """移除多表模块中的所有活跃表时，删除整个模块文件。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    (test_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "TABLE_A = Table(name='table_a', columns=[])\n"
        "TABLE_B = Table(name='table_b', columns=[])\n",
        encoding="utf-8",
    )
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .config import TABLE_A, TABLE_B",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, TABLE_A, TABLE_B]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "table_a", "table_b")

    assert not (test_dir / "config.py").exists()
    init_after = (test_dir / "__init__.py").read_text()
    assert "TABLE_A" not in init_after
    assert "TABLE_B" not in init_after
    assert "BUDDY_LIST" in init_after


def test_remove_multiple_mixed_modules(tmp_path: Path) -> None:
    """同时移除来自不同模块类型的表（单表 + 多表）。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])

    test_dir = tmp_path / "test"
    (test_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "from ..base import Table\n"
        "TABLE_A = Table(name='table_a', columns=[])\n"
        "TABLE_B = Table(name='table_b', columns=[])\n",
        encoding="utf-8",
    )
    init_content = (test_dir / "__init__.py").read_text()
    init_content = init_content.replace(
        "from .buddy_list import BUDDY_LIST",
        "from .buddy_list import BUDDY_LIST\nfrom .config import TABLE_A, TABLE_B",
    )
    init_content = init_content.replace(
        "tables=[BUDDY_LIST]",
        "tables=[BUDDY_LIST, TABLE_A, TABLE_B]",
    )
    (test_dir / "__init__.py").write_text(init_content)

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        remove_table("test.db", "buddy_list", "table_a")

    # buddy_list 是单表模块 → 文件删除
    assert not (test_dir / "buddy_list.py").exists()
    # config 是多表模块，TABLE_B 还在 → 文件保留
    assert (test_dir / "config.py").exists()
    config_content = (test_dir / "config.py").read_text()
    assert "TABLE_B" in config_content
    assert "TABLE_A" not in config_content

    init_after = (test_dir / "__init__.py").read_text()
    assert "BUDDY_LIST" not in init_after
    assert "TABLE_A" not in init_after
    assert "TABLE_B" in init_after


def test_remove_empty_table_names_raises(tmp_path: Path) -> None:
    """未指定任何表名时 raise ValueError。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list"])
        with pytest.raises(ValueError, match="至少需要指定一个表名"):
            remove_table("test.db")


def test_remove_multiple_fail_fast_on_second(tmp_path: Path) -> None:
    """多表移除时第二个表不存在应 raise 且不修改任何文件。"""
    _write_schema_files(tmp_path)
    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        add_db("test.db", ["buddy_list", "group_list"])

    with patch("dbtools.codegen.core._SCHEMA_DIR", tmp_path):
        with pytest.raises(ValueError, match="not found"):
            remove_table("test.db", "buddy_list", "no_such_table")

    # 第一个表应保持未被移除
    assert (tmp_path / "test" / "buddy_list.py").exists()
    assert (tmp_path / "test" / "group_list.py").exists()
    init_content = (tmp_path / "test" / "__init__.py").read_text()
    assert "BUDDY_LIST" in init_content
    assert "GROUP_LIST" in init_content
