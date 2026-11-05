"""list-columns: 列出 -t 指定的表里的列及其映射状态。"""

import argparse
import sqlite3
import sys

from cmds._status import STATUS_LABELS
from db.schema import columns
from mapping.columns import column_mappings, mapping_of
from render.dispatch import show
from render.sheet import Column, Sheet

__all__ = ["run"]


def run(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    infos = columns(conn, args.table)
    if not infos:
        sys.exit(f"表不存在: {args.table}")
    mappings = column_mappings(args.db, args.table)
    rows, styles = [], []
    for info in infos:
        mapping = mapping_of(mappings, info.name)
        status = STATUS_LABELS[mapping.status]
        rows.append((info.cid, info.name, info.type, mapping.label or "", status.text, info.pk or None))
        styles.append(status.style)
    header = [Column("序号", align="right"), Column("列名"), Column("类型"), Column("语义"), Column("状态"), Column("主键", align="right", null_text="")]
    show(Sheet(header, rows, title=args.table, row_styles=styles), form=args.form)
