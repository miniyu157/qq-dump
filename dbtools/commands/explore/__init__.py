"""Schema 探索 —— 对比 schema 声明与本地数据库文件的实际结构。

用法:
    python -m dbtools explore -d <db_dir>                   # L1: 所有数据库
    python -m dbtools explore -d <db_dir> <db>              # L2: 特定数据库的表
    python -m dbtools explore -d <db_dir> <db> <table>      # L3: 特定表的字段

标注:
    [+]  DB 有、schema 未定义 → 待补充（红色，行动项）
    [-]  schema 有、DB 未包含 → 仅参考（dim，多为旧版本 DB）
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape
from rich.rule import Rule

from ._common import _discover_schemas, console
from ._render import (
    render_all_tables_report,
    render_all_tables_summary,
    render_field_summary,
    render_schema_report,
    render_schema_summary,
    render_table_report,
)
from ...schema.base import Database, Table as SchemaTable


# ═══════════════════════════════════════════════════════════════════════════════
# 分发函数 —— 查找 schema 对象，调用渲染，返回统计数据。不含任何渲染逻辑。
# ═══════════════════════════════════════════════════════════════════════════════


def _find_db(schemas: list[Database], filename: str) -> Database | None:
    """按 filename 查找 Database，未找到返回 None。"""
    for db in schemas:
        if db.filename == filename:
            return db
    return None


def _dispatch_table_level(
    schemas: list[Database], db_filename: str, table_name: str, db_dir: Path,
) -> tuple[SchemaTable, int, int, set[str]]:
    """L3: 查找 DB/表 → 调用渲染 → 返回统计数据。"""
    schema_db = _find_db(schemas, db_filename)
    if schema_db is None:
        console.print(f"[red]schema 中未找到数据库: {escape(db_filename)}[/red]")
        console.print(f"  已知数据库: {escape(', '.join(db.filename for db in schemas))}")
        raise typer.Exit(code=1)

    try:
        schema_table = schema_db.table(table_name)
    except KeyError:
        console.print(f"[red]数据库 {escape(db_filename)} 的 schema 中未找到表: {escape(table_name)}[/red]")
        console.print(f"  已知表: {escape(', '.join(t.name for t in schema_db.tables))}")
        raise typer.Exit(code=1)

    files_found, has_table, all_schema_missing = render_table_report(
        schema_table, db_filename, db_dir,
    )
    return schema_table, files_found, has_table, all_schema_missing


def _dispatch_all_tables(
    schemas: list[Database], db_filename: str, db_dir: Path,
) -> tuple[int, int, int, int]:
    """L2.5: 查找 DB → 调用 all-tables 渲染 → 返回聚合统计。"""
    schema_db = _find_db(schemas, db_filename)
    if schema_db is None:
        console.print(f"[red]schema 中未找到数据库: {escape(db_filename)}[/red]")
        console.print(f"  已知数据库: {escape(', '.join(db.filename for db in schemas))}")
        raise typer.Exit(code=1)

    return render_all_tables_report(schema_db, db_dir)


def _dispatch_schema_level(
    schemas: list[Database], db_filename: str | None, db_dir: Path, include_fts: bool,
) -> tuple[int, int, int, set[str]]:
    """L1/L2: 构建目标列表 → 逐库调用渲染 → 返回聚合统计数据。"""
    if db_filename is not None:
        schema_db = _find_db(schemas, db_filename)
        if schema_db is None:
            console.print(f"[red]schema 中未找到数据库: {escape(db_filename)}[/red]")
            console.print(f"  已知数据库: {escape(', '.join(db.filename for db in schemas))}")
            raise typer.Exit(code=1)
        targets = [schema_db]
    else:
        targets = schemas

    total_files = total_readable = total_schema_tables = 0
    all_schema_missing: set[str] = set()

    for db in targets:
        files_found, readable, schema_missing = render_schema_report(
            db, db_dir, include_fts=include_fts,
        )
        total_files += files_found
        total_readable += readable
        total_schema_tables += len(db.tables)
        all_schema_missing |= schema_missing

    return total_files, total_readable, total_schema_tables, all_schema_missing


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 命令 —— 参数定义 → 校验 → 调用分发 → 渲染摘要
# ═══════════════════════════════════════════════════════════════════════════════


def explore(
    ctx: typer.Context,
    db_dir: Path = typer.Option(
        ..., "--db-dir", "-d",
        help="包含已解密 *.db 文件的目录路径。",
        exists=True, file_okay=False, dir_okay=True, resolve_path=True,
    ),
    db_filename: str | None = typer.Argument(
        None, help="数据库文件名，如 profile_info.db。不指定则对比所有数据库。",
    ),
    table_name: str | None = typer.Argument(
        None, help="表名，如 profile_info_v6。必须同时指定数据库文件名。",
    ),
    include_fts: bool = typer.Option(
        False, "--fts", "-F",
        help="解析数据库中的 *_fts 全文索引表，将其计入覆盖率差异。",
    ),
    all_tables: bool = typer.Option(
        False, "--all-tables", "-a",
        help="当指定数据库时，输出该数据库中所有表的字段覆盖率（紧凑单表视图）。",
    ),
) -> None:
    """探索本地 QQNT 数据库，对比 schema 定义与实际结构。"""

    if table_name is not None and db_filename is None:
        console.print("[red]错误：指定表名时必须同时指定数据库文件名。[/red]")
        raise typer.Exit(code=1)

    if all_tables and db_filename is None:
        console.print("[red]错误：使用 --all-tables/-a 时必须指定数据库文件名。[/red]")
        raise typer.Exit(code=1)

    if all_tables and table_name is not None:
        console.print("[red]错误：--all-tables/-a 与指定表名互斥。[/red]")
        raise typer.Exit(code=1)

    schemas = _discover_schemas()
    if not schemas:
        console.print("[red]dbtools.schema 中未找到任何 Database 定义。[/red]")
        raise typer.Exit(code=1)

    # ── L2.5: 数据库级全表字段覆盖率 ──
    if all_tables:
        console.print(Rule("[bold]全表字段覆盖率报告[/bold]"))
        total_tables, fully_covered, tables_with_missing, total_missing = _dispatch_all_tables(
            schemas, db_filename, db_dir,
        )
        render_all_tables_summary(total_tables, fully_covered, tables_with_missing, total_missing)
        return

    # ── L3: 表级字段覆盖率 ──
    if table_name is not None:
        console.print(Rule("[bold]表字段覆盖率报告[/bold]"))
        schema_table, files_found, has_table, all_schema_missing = _dispatch_table_level(
            schemas, db_filename, table_name, db_dir,
        )
        render_field_summary(schema_table, files_found, has_table, all_schema_missing)
        return

    # ── L1/L2: schema 级表覆盖率 ──
    console.print(Rule("[bold]Schema 解析覆盖率报告[/bold]"))
    total_files, total_readable, total_schema_tables, all_schema_missing = _dispatch_schema_level(
        schemas, db_filename, db_dir, include_fts,
    )
    render_schema_summary(total_files, total_readable, total_schema_tables, all_schema_missing)


__all__ = ["explore"]
