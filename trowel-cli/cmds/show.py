"""show: 按 rowid 升序渲染 -t 指定的整张表。"""

import argparse
import sqlite3
import sys

from cmds._status import STATUS_LABELS
from db.rows import table_rows
from db.schema import columns
from lib.wire import parse_fields
from mapping.columns import column_mappings, mapping_of
from maps import Status
from render.dispatch import show
from render.sheet import Cell, Column, Sheet
from render.tip import render_tip

__all__ = ["parse_statuses", "run"]

_STATUS_LETTERS = {"u": Status.UNDEFINED, "h": Status.HIDDEN, "d": Status.DISCARDED}


def parse_statuses(raw: str) -> frozenset[Status]:
    """-C/-P 后缀的 argparse type，由 u/h/d 任意组合。"""
    if not raw or any(letter not in _STATUS_LETTERS for letter in raw):
        raise argparse.ArgumentTypeError(f"后缀只能由 u/h/d 组成: {raw}")
    return frozenset(_STATUS_LETTERS[letter] for letter in raw)


def _concealed(groups: list[frozenset[Status]] | None) -> frozenset[Status]:
    """默认不显示的状态，去掉 -C 选中的部分；已定义与探索中不在其中，始终显示。"""
    revealed = frozenset().union(*groups) if groups else frozenset()
    return frozenset(_STATUS_LETTERS.values()) - revealed


def _cell(value: object) -> Cell:
    """BLOB 只显示类别：整段能解析出 protobuf 字段时为 (protobuf)，否则为 (blob)。"""
    if isinstance(value, bytes):
        return "(protobuf)" if parse_fields(value) else "(blob)"
    return value


def run(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    if not columns(conn, args.table):
        sys.exit(f"表不存在: {args.table}")
    mappings = column_mappings(args.db, args.table)
    concealed = _concealed(args.columns)
    data = table_rows(conn, args.table, last=args.last)
    header, kept = [], []
    for index, name in enumerate(data.names):
        mapping = mapping_of(mappings, name)
        if mapping.status in concealed:
            continue
        kept.append(index)
        title = f"{name}({mapping.label})" if args.name and mapping.label else name
        header.append(Column(title, style=STATUS_LABELS[mapping.status].style))
    rows = [tuple(_cell(row[index]) for index in kept) for row in data.values]
    show(Sheet(header, rows, title=args.table, row_ids=data.row_ids), form=args.form)
    hidden = len(data.names) - len(kept)
    if hidden and not args.no_summary:
        amount = f"全部 {hidden} 个列未显示" if hidden == len(data.names) else f"有 {hidden} 个列未显示"
        render_tip([f"{amount}，可以使用 -C 或 -C[uhd] 重新显示。"])
