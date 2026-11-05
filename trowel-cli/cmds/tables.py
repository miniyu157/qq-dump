"""tables: 列出所有表、行数与已定义列的比例。"""

import argparse
import sqlite3

from db.schema import TableInfo, columns, tables
from mapping.columns import column_mappings
from render.dispatch import show
from render.sheet import Column, Sheet

__all__ = ["run"]


def _defined_count(conn: sqlite3.Connection, args: argparse.Namespace, table: str) -> tuple[int, int]:
    """(maps/ 中登记的列数, 表的列数)；只比对列名，不区分状态，列含虚拟表的隐藏列。"""
    mappings = column_mappings(args.db, table)
    names = [info.name for info in columns(conn, table)]
    return sum(name in mappings for name in names), len(names)


def _coverage_text(defined: int, total: int) -> str:
    if not total:
        return "0/0"
    return f"{defined}/{total} ({defined / total:.1%})"


def _table_style(table: TableInfo, defined: int, total: int) -> str | None:
    """颜色按列数判定，不按显示的百分比: 99.96% 显示为 100.0% 时仍为黄色。"""
    parts = []
    if table.rows == 0:
        parts.append("dim")
    if total and defined == total:
        parts.append("green")
    elif defined:
        parts.append("yellow")
    return " ".join(parts) or None


def run(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    infos = [(table, *_defined_count(conn, args, table.name)) for table in tables(conn)]
    rows = [(table.name, table.rows, _coverage_text(defined, total)) for table, defined, total in infos]
    styles = [_table_style(table, defined, total) for table, defined, total in infos]
    header = [Column("表"), Column("行数", align="right"), Column("已定义列", align="right")]
    show(Sheet(header, rows, row_styles=styles), form=args.form)
