"""explore 命令共享工具：覆盖率运算、schema 发现、数据库读取、Rich 控制台。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

import dbtools.schema as _schema

from ...schema.base import Database

# ── Rich Console ──────────────────────────────────────────────────────────────

console = Console()


# ── Schema 发现 ──────────────────────────────────────────────────────────────


def _discover_schemas() -> list[Database]:
    """从 dbtools.schema 公开 API 中提取所有 Database 实例。"""
    result: list[Database] = []
    for name in _schema.__all__:
        obj = getattr(_schema, name, None)
        if isinstance(obj, Database):
            result.append(obj)
    return result


# ── 覆盖率运算 ───────────────────────────────────────────────────────────────


@dataclass
class CoverageResult:
    """一次 schema-vs-actual 集合对比的量化结果。

    分母永远是本地实际数量（actual），而非 schema 定义数量。
    """

    covered: int
    actual: int          # 分母 = 本地 DB 实际数量
    schema_count: int    # schema 定义总量
    schema_missing: set[str]  # 本地有、schema 缺失 → 需补充
    db_missing: set[str]      # schema 有、本地缺失 → 仅参考

    @property
    def pct(self) -> float:
        """解析覆盖率 = covered / actual × 100。"""
        return self.covered / self.actual * 100 if self.actual else 100


@dataclass
class AllTablesTableResult:
    """L2.5 单表字段覆盖率的聚合结果（跨所有本地文件取并集）。"""

    table_name: str
    schema_field_count: int       # schema 中定义的字段数
    files_found: int              # 匹配的本地文件总数
    files_with_table: int         # 包含此表的文件数
    covered: int                  # schema 与实际并集的交集大小
    actual: int                   # 所有文件中实际列 ID 的并集大小
    schema_missing: set[str]      # 实际有、schema 缺失的列 ID 并集
    missing_types: dict[str, str] # 缺失列 ID → SQL 类型（来自 PRAGMA）


def _compute_coverage(schema_set: set[str], actual_set: set[str]) -> CoverageResult:
    """对两个集合执行覆盖率运算，返回 CoverageResult。"""
    return CoverageResult(
        covered=len(schema_set & actual_set),
        actual=len(actual_set),
        schema_count=len(schema_set),
        schema_missing=actual_set - schema_set,
        db_missing=schema_set - actual_set,
    )


def _safe_sort_key(s: str) -> tuple[int, int | str]:
    """安全的排序键：数字字符串按整数值排序，非数字字符串排在最后。"""
    return (0, int(s)) if s.isdigit() else (1, s)


def _union_column_types(
    schema_missing: set[str],
    all_file_cols: list[dict[str, str]],
) -> dict[str, str]:
    """为 schema_missing 中的每个列 ID 解析其 SQL 类型。

    从第一个包含该列的文件中获取类型。列 ID 保证至少在一个
    all_file_cols 中存在（因为 schema_missing 就是从 actual_set - schema_set 得出）。
    """
    result: dict[str, str] = {}
    for cid in schema_missing:
        for file_cols in all_file_cols:
            if cid in file_cols:
                result[cid] = file_cols[cid]
                break
    return result


# ── SQLite 读取 ──────────────────────────────────────────────────────────────

# SQLite FTS3/4/5 影子表后缀 —— 这些表由 FTS 引擎内部维护，业务代码不应直接操作
_FTS_SHADOW_SUFFIXES = (
    "_config", "_content", "_data", "_docsize", "_idx",
    "_segdir", "_segments", "_stat",
)


def _get_actual_tables(db_path: Path) -> list[str]:
    """返回 SQLite 文件中所有业务表名称，排除 SQLite 内部表及 FTS 影子表。"""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' "
            "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
            "ORDER BY name"
        ).fetchall()
    all_tables = [r[0] for r in rows]
    table_set = set(all_tables)

    result: list[str] = []
    for name in all_tables:
        is_shadow = False
        for suffix in _FTS_SHADOW_SUFFIXES:
            if name.endswith(suffix) and name[: -len(suffix)] in table_set:
                is_shadow = True
                break
        if not is_shadow:
            result.append(name)
    return result


def _get_actual_columns(db_path: Path, table_name: str) -> dict[str, str]:
    """返回表中所有列名到类型的映射。键为列名（QQNT 数字字符串），值为 SQL 类型。"""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {r[1]: r[2] for r in rows}  # r[1]=name, r[2]=type
