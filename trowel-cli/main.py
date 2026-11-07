#!/usr/bin/env python3
"""Trowel: 查看已解密 SQLite 数据库的表与列。"""

import sys

from app.usage import parse_args, print_database_operations, print_databases, print_table_operations, usage_error
from cmds import list_columns, show, tables
from config.catalog import available_databases, available_tables
from config.dotfile import load_config, resolve_db
from db.connection import is_sqlite_file, open_readonly
from db.schema import columns, table_names

# 键与 app.usage 中的操作名一致
_RUNS = {"tables": tables.run, "list-columns": list_columns.run, "show": show.run}


def main() -> None:
    args = parse_args()
    config = load_config()
    if args.db is None:
        print_databases(available_databases(config))
        sys.exit(2)

    args.db = resolve_db(config, args.db)
    if args.table is not None:
        args.table = config.table_aliases.get(args.table, args.table)
    if not is_sqlite_file(args.db):
        usage_error(f"不是 SQLite 数据库文件: {args.db}")
    conn = open_readonly(args.db)

    if args.operation is None:
        if args.table is None:
            print_database_operations(args.db.name, available_tables(config, table_names(conn)))
        elif not columns(conn, args.table):
            sys.exit(f"表不存在: {args.table}")
        else:
            print_table_operations(args.table)
        sys.exit(2)

    _RUNS[args.operation](conn, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
