"""explore 命令的渲染层 —— 所有 Rich 表格输出集中在此模块。

__init__.py（分发器）不直接构建任何 RichTable，只调用本模块的函数。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rich import box
from rich.markup import escape
from rich.table import Table as RichTable

from ._common import (
    _compute_coverage,
    _get_actual_columns,
    _get_actual_tables,
    _safe_sort_key,
    _union_column_types,
    console,
)
from ...schema.base import Database, Table as SchemaTable


def _pct_style(pct: float) -> str:
    """覆盖率 Rich 颜色标记。"""
    if pct >= 100:
        return f"[green]{pct:.1f}%[/green]"
    if pct >= 80:
        return f"[yellow]{pct:.1f}%[/yellow]"
    return f"[red]{pct:.1f}%[/red]"


# ═══════════════════════════════════════════════════════════════════════════════
# 详情表渲染
# ═══════════════════════════════════════════════════════════════════════════════


def render_schema_report(
    db: Database, db_dir: Path, *, include_fts: bool = False,
) -> tuple[int, int, set[str]]:
    """输出单库的表覆盖率 ASCII 报告。

    Returns:
        (files_found, files_readable, union_of_schema_missing)
    """
    pattern = f"*.{db.filename}"
    files = sorted(db_dir.glob(pattern))
    schema_names = {t.name for t in db.tables}
    all_schema_missing: set[str] = set()

    console.print(
        f"[bold cyan]{escape(db.filename)}[/bold cyan]  —  "
        f"schema 定义 {len(db.tables)} 张表，{len(files)} 个本地文件",
        justify="center",
    )

    if not files:
        console.print("  [dim]（无本地文件）[/dim]")
        return 0, 0, all_schema_missing

    table = RichTable(box=box.ASCII2, show_header=True, header_style="bold")
    table.add_column("文件", style="cyan")
    table.add_column("定义/实际", justify="center")
    table.add_column("解析覆盖率", justify="center")
    table.add_column("备注")

    readable = 0
    for fp in files:
        try:
            actual = _get_actual_tables(fp)
        except sqlite3.DatabaseError as exc:
            table.add_row(
                escape(fp.name), "[red]ERR[/red]", "—",
                f"[red]无法读取: {escape(str(exc))}[/red]",
            )
            continue

        readable += 1
        actual_set = set(actual)
        if not include_fts:
            actual_set = {t for t in actual_set if not t.endswith("_fts")}

        cr = _compute_coverage(schema_names, actual_set)
        all_schema_missing |= cr.schema_missing

        notes: list[str] = []
        if cr.schema_missing:
            notes.append(
                f"[red][+] Schema 缺失 ({len(cr.schema_missing)}): "
                f"{escape(', '.join(sorted(cr.schema_missing)))}[/red]"
            )
        if cr.db_missing:
            notes.append(
                f"[dim][-] DB 未包含 ({len(cr.db_missing)}): "
                f"{escape(', '.join(sorted(cr.db_missing)))}[/dim]"
            )
        if not notes:
            notes.append("[green]完全匹配[/green]")

        table.add_row(
            escape(fp.name),
            f"{cr.schema_count}/{cr.actual}",
            f"{cr.covered}/{cr.actual}  {_pct_style(cr.pct)}",
            "\n".join(notes),
        )

    console.print(table)
    return len(files), readable, all_schema_missing


def render_table_report(
    schema_table: SchemaTable, db_filename: str, db_dir: Path,
) -> tuple[int, int, set[str]]:
    """输出单表的字段覆盖率 ASCII 报告。

    Returns:
        (files_found, files_with_table, union_of_schema_missing)
    """
    schema_fields = {f.id: f for f in schema_table.columns}
    pattern = f"*.{db_filename}"
    files = sorted(db_dir.glob(pattern))
    all_schema_missing: set[str] = set()

    console.print(
        f"[bold cyan]{escape(schema_table.name)}[/bold cyan]  "
        f"({escape(db_filename)})  —  "
        f"schema 定义 {len(schema_fields)} 个字段，{len(files)} 个本地文件",
        justify="center",
    )

    if not files:
        console.print("  [dim]（无本地文件）[/dim]")
        return 0, 0, all_schema_missing

    table = RichTable(box=box.ASCII2, show_header=True, header_style="bold")
    table.add_column("文件", style="cyan")
    table.add_column("定义/实际", justify="center")
    table.add_column("字段覆盖率", justify="center")
    table.add_column("备注")

    has_table = 0
    for fp in files:
        try:
            actual_cols = _get_actual_columns(fp, schema_table.name)
        except sqlite3.DatabaseError as exc:
            table.add_row(
                escape(fp.name), "[red]ERR[/red]", "—",
                f"[red]无法读取: {escape(str(exc))}[/red]",
            )
            continue

        if not actual_cols:
            table.add_row(
                escape(fp.name), "—", "—",
                "[dim]表不存在于此文件中[/dim]",
            )
            continue

        has_table += 1
        actual_ids = set(actual_cols.keys())
        schema_ids = set(schema_fields.keys())

        cr = _compute_coverage(schema_ids, actual_ids)
        all_schema_missing |= cr.schema_missing

        notes: list[str] = []
        if cr.schema_missing:
            detail = ", ".join(
                f"#{escape(cid)} ({escape(actual_cols[cid])})"
                for cid in sorted(cr.schema_missing, key=_safe_sort_key)
            )
            notes.append(f"[red][+] Schema 缺失 ({len(cr.schema_missing)}): {detail}[/red]")
        if cr.db_missing:
            detail = ", ".join(
                f"{escape(schema_fields[fid].name)} (#{escape(fid)}, {escape(schema_fields[fid].field_type)})"
                for fid in sorted(cr.db_missing, key=_safe_sort_key)
            )
            notes.append(f"[dim][-] DB 未包含 ({len(cr.db_missing)}): {detail}[/dim]")
        if not notes:
            notes.append("[green]完全匹配[/green]")

        table.add_row(
            escape(fp.name),
            f"{cr.schema_count}/{cr.actual}",
            f"{cr.covered}/{cr.actual}  {_pct_style(cr.pct)}",
            "\n".join(notes),
        )

    console.print(table)
    return len(files), has_table, all_schema_missing


def render_all_tables_report(
    schema_db: Database, db_dir: Path,
) -> tuple[int, int, int, int]:
    """L2.5: 紧凑单表视图 —— 每张 schema 表一行，显示字段覆盖率。

    对每张 schema 表遍历所有匹配 DB 文件，跨文件取实际列 ID 和
    schema_missing 的并集，计算字段级覆盖率。

    Returns:
        (total_tables, fully_covered, tables_with_missing, total_missing_fields)
    """
    pattern = f"*.{schema_db.filename}"
    files = sorted(db_dir.glob(pattern))

    console.print(
        f"[bold cyan]{escape(schema_db.filename)}[/bold cyan]  —  "
        f"所有表的字段覆盖率",
        justify="center",
    )

    if not files:
        console.print("  [dim]（无本地文件）[/dim]")
        return 0, 0, 0, 0

    if not schema_db.tables:
        console.print("  [dim]该数据库 schema 中未定义任何表[/dim]")
        return 0, 0, 0, 0

    table = RichTable(box=box.ASCII2, show_header=True, header_style="bold")
    table.add_column("表名", style="cyan")
    table.add_column("本地文件数", justify="center")
    table.add_column("字段覆盖率", justify="center")
    table.add_column("待补充字段")

    fully_covered = 0
    total_missing = 0

    for schema_table in schema_db.tables:
        schema_ids = {f.id for f in schema_table.columns}
        union_actual: set[str] = set()
        union_schema_missing: set[str] = set()
        all_file_cols: list[dict[str, str]] = []
        files_with = 0

        for fp in files:
            try:
                actual_cols = _get_actual_columns(fp, schema_table.name)
            except sqlite3.DatabaseError:
                continue

            if not actual_cols:
                continue

            files_with += 1
            all_file_cols.append(actual_cols)
            actual_ids = set(actual_cols.keys())
            union_actual |= actual_ids
            union_schema_missing |= (actual_ids - schema_ids)

        if files_with == 0:
            table.add_row(
                escape(schema_table.name),
                f"[dim]0/{len(files)}[/dim]",
                "—",
                "[dim]表中无此表[/dim]",
            )
            continue

        cr = _compute_coverage(schema_ids, union_actual)
        missing_types = _union_column_types(union_schema_missing, all_file_cols)

        if not union_schema_missing:
            fully_covered += 1
            notes = "[green]无[/green]"
        else:
            detail = ", ".join(
                f"#{escape(cid)} ({escape(missing_types[cid])})"
                if cid in missing_types
                else f"#{escape(cid)}"
                for cid in sorted(union_schema_missing, key=_safe_sort_key)
            )
            notes = f"[red]{len(union_schema_missing)}: {detail}[/red]"
            total_missing += len(union_schema_missing)

        table.add_row(
            escape(schema_table.name),
            f"{files_with}/{len(files)}",
            f"{cr.covered}/{cr.actual}  {_pct_style(cr.pct)}",
            notes,
        )

    console.print(table)
    tables_with_missing = len(schema_db.tables) - fully_covered
    return len(schema_db.tables), fully_covered, tables_with_missing, total_missing


# ═══════════════════════════════════════════════════════════════════════════════
# 汇总表渲染
# ═══════════════════════════════════════════════════════════════════════════════


def render_field_summary(
    schema_table: SchemaTable,
    files_found: int,
    has_table: int,
    all_schema_missing: set[str],
) -> None:
    """L3: 输出表级字段覆盖率汇总。"""
    console.print("汇总", justify="center")
    s = RichTable(box=box.ASCII2, show_header=False, pad_edge=False)
    s.add_column(style="bold")
    s.add_column()
    s.add_row("Schema 字段数", str(len(schema_table.columns)))
    s.add_row("本地 DB 文件", f"{files_found}  （包含此表: {has_table}）")
    if all_schema_missing:
        missing_str = ", ".join(
            f"#{escape(cid)}" for cid in sorted(all_schema_missing, key=_safe_sort_key)
        )
        s.add_row("待补充到 Schema", f"[red]{len(all_schema_missing)}  ({missing_str})[/red]")
    else:
        s.add_row("待补充到 Schema", "[green]无[/green]")
    console.print(s)


def render_all_tables_summary(
    total_tables: int,
    fully_covered: int,
    tables_with_missing: int,
    total_missing_fields: int,
) -> None:
    """L2.5: 全表字段覆盖率汇总。"""
    console.print("汇总", justify="center")
    s = RichTable(box=box.ASCII2, show_header=False, pad_edge=False)
    s.add_column(style="bold")
    s.add_column()
    s.add_row("总表数", str(total_tables))
    s.add_row("完全覆盖", str(fully_covered))
    s.add_row("存在缺失", str(tables_with_missing))
    if total_missing_fields:
        s.add_row("待补充字段总数", f"[red]{total_missing_fields}[/red]")
    else:
        s.add_row("待补充字段总数", "[green]0[/green]")
    console.print(s)


def render_schema_summary(
    total_files: int,
    total_readable: int,
    total_schema_tables: int,
    all_schema_missing: set[str],
) -> None:
    """L1/L2: 输出 schema 级表覆盖率汇总。"""
    console.print("汇总", justify="center")
    s = RichTable(box=box.ASCII2, show_header=False, pad_edge=False)
    s.add_column(style="bold")
    s.add_column()
    s.add_row("Schema 定义总表数", str(total_schema_tables))
    s.add_row(
        "扫描文件数",
        f"{total_files}  （可读: {total_readable}, 无法读取: {total_files - total_readable}）",
    )
    if all_schema_missing:
        s.add_row(
            "待补充到 Schema",
            f"[red]{len(all_schema_missing)}  ({escape(', '.join(sorted(all_schema_missing)))})[/red]",
        )
    else:
        s.add_row("待补充到 Schema", "[green]无[/green]")
    console.print(s)
