#!/usr/bin/env python3
"""Trowel: 查看已解密 SQLite 数据库的表与列。"""

import sys

from app.dotfile import ConfigError, load_config, resolve_db
from app.usage import fail, parse_args, print_table_operations, usage_error
from cmds import list_columns, list_files, preview_tables, show, tables
from db.connection import is_sqlite_file, open_readonly
from db.schema import MissingTable, require_table

# 键与 app.usage 中的操作名一致；+list-files 与 +preview-tables 需要配置，在 main 中单独调用
_RUNS = {"tables": tables.run, "list-columns": list_columns.run, "show": show.run}


def main() -> None:
    args = parse_args()
    config = load_config()
    if args.operation == "list-files":
        list_files.run(config)
        return

    args.db = resolve_db(config, args.db)
    if args.table is not None:
        args.table = config.table_aliases.get(args.table, args.table)
    if not is_sqlite_file(args.db):
        usage_error(f"不是 SQLite 数据库文件: {args.db}")
    conn = open_readonly(args.db)

    if args.operation is None:
        require_table(conn, args.table)
        print_table_operations(args.table)
        sys.exit(2)
    if args.operation == "preview-tables":
        preview_tables.run(conn, config, args)
        return
    _RUNS[args.operation](conn, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except ConfigError as error:
        fail(str(error))
    except MissingTable as error:
        usage_error(f"表不存在: {error}")
