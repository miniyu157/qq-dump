#!/usr/bin/env python3
"""Trowel: 查看已解密 SQLite 数据库的表与列。"""

import argparse
import sys
from pathlib import Path

from cmds import list_columns, show, tables
from db.connection import is_sqlite_file, open_readonly


def _non_negative(raw: str) -> int:
    if not raw.isdigit():
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}")
    return int(raw)


def main() -> None:
    parser = argparse.ArgumentParser(prog="main.py", description="查看已解密 SQLite 数据库的表与列。")
    parser.add_argument("-d", "--db", type=Path, metavar="<file>", help="要读取的数据库文件")
    parser.add_argument("-t", "--table", metavar="<table>", help="要查看的表")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("-k", "--kv", dest="form", action="store_const", const="kv", help="输出为键值对")
    form.add_argument("-j", "--json", dest="form", action="store_const", const="json", help="输出为 JSON")
    parser.set_defaults(form="table", needs_table=False)
    sub = parser.add_subparsers(dest="command", title="子命令", metavar="<subcommand>")
    sub.add_parser("tables", help="列出所有表及行数").set_defaults(func=tables.run)
    sub.add_parser("list-columns", help="列出 -t 指定的表里的列").set_defaults(func=list_columns.run, needs_table=True)
    show_parser = sub.add_parser("show", help="按 rowid 升序渲染 -t 指定的整张表")
    show_parser.add_argument("-l", "--last", type=_non_negative, metavar="N", help="只取末尾 N 行")
    show_parser.add_argument("-C", "--columns", nargs="?", const="uhd", type=show.parse_statuses, action="append", metavar="uhd", help="另外显示未定义 (u)、已隐藏 (h)、已丢弃 (d) 的列，省略后缀时全部显示")
    show_parser.add_argument("-P", "--fields", nargs="?", const="uhd", type=show.parse_statuses, action="append", metavar="uhd", help="protobuf 字段的显示范围，尚未生效")
    show_parser.add_argument("-n", "--name", action="store_true", help="列名后附加 maps 中的语义名称")
    show_parser.add_argument("-q", "--no-summary", action="store_true", help="不显示末尾的摘要")
    show_parser.set_defaults(func=show.run, needs_table=True)
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(2)
    if args.db is None:
        parser.error("需要 -d 指定数据库")
    if not is_sqlite_file(args.db):
        parser.error(f"不是 SQLite 数据库文件: {args.db}")
    if args.needs_table and args.table is None:
        parser.error(f"{args.command} 需要 -t 指定表")

    args.func(open_readonly(args.db), args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
