"""+preview-tables: 列出库中的表与表别名，不统计行数。"""

import argparse
import sqlite3

from rich.text import Text

from app.dotfile import Config
from cmds._listing import Entry, print_group, stdout
from db.schema import table_names

__all__ = ["run"]


def _entries(config: Config, names: list[str]) -> list[Entry]:
    """names 中的表及指向它们的表别名；目标不在 names 中的别名属于其他数据库，不列出。"""
    return [Entry(name, [alias for alias, target in config.table_aliases.items() if target == name]) for name in names]


def run(conn: sqlite3.Connection, config: Config, args: argparse.Namespace) -> None:
    print_group(stdout(), Text.assemble((args.db.name, "bold pink1"), " 中的表:", style="bold"), _entries(config, table_names(conn)))
