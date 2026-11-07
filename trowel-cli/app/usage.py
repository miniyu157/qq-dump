"""命令行解析与全部用法文案: 帮助、用法错误，以及未指定数据库或操作时的提示。

帮助打印到 stdout，其余打印到 stderr；对应的流不是终端时不着色。
"""

import argparse
import sys
from collections.abc import Sequence
from typing import NamedTuple, NoReturn

from rich.console import Console
from rich.text import Text

from cmds.show import parse_statuses
from config.catalog import Catalog, TableEntry

__all__ = ["parse_args", "print_database_operations", "print_databases", "print_table_operations", "usage_error"]

_PROG = "trowel"
_USAGE = r"[bold]trowel[/] \[选项] <db> \[<table>] <操作> \[操作选项]"

_HELP = rf"""[bold]TROWEL -- 查看已解密 SQLite 数据库的表与列[/]

[bold underline]用法:[/]
  {_USAGE}

[bold underline]参数:[/]
  [bold]db[/]                        数据库别名、工作区中的名称 (可省略 .db)，
                            或含 / 的路径
  [bold]table[/]                     表或表别名

[bold underline]操作 (数据库):[/]
  [bold pink1]--tables[/]                  查看所有表和行数，以知识覆盖进行着色

[bold underline]操作 (表):[/]
  [bold pink1]--list-columns[/]            列出表里的列，以知识覆盖进行着色
  [bold pink1]--show[/]                    按 rowid 升序渲染整张表
    [bold]-l, --last N[/]            只取末尾 N 行
    [bold]-C, --columns \[uhd][/]     另外显示未定义 (u)、已隐藏 (h)、
                            已丢弃 (d) 的列，省略后缀时全部显示
    [bold]-P, --fields \[uhd][/]      protobuf 字段的显示范围，[dim]尚未生效[/]
    [bold]-n, --name[/]              列名后附加 maps 中的语义名称
    [bold]-q, --no-summary[/]        不显示末尾的摘要

[bold underline]选项 (输出):[/]
  [bold]-k, --kv[/]                  输出为键值对
  [bold]-j, --json[/]                输出为 JSON

[bold underline]配置:[/]
  [dim]启动时读取 CWD 下的 .trowel (每行 KEY=VALUE，# 开头为注释)，
  同名环境变量优先，别名与真实名称同名时以别名为准。[/]
  [bold]TROWEL_WORKSPACE=<dir>[/]        不含 / 的 <db> 在此查找，未设置时为 CWD
  [bold]TROWEL_DB_<alias>=<db>[/]        数据库别名，目标按 <db> 的规则解析
  [bold]TROWEL_TABLE_<alias>=<table>[/]  表别名，对所有数据库生效

[bold underline]选项 (程序):[/]
  [bold]-h, --help[/]                显示本帮助
"""


class _Operation(NamedTuple):
    """on_table 为 True 时必须指定表，否则不能指定表。"""

    on_table: bool
    help: str


_OPERATIONS = {
    "tables": _Operation(on_table=False, help="查看所有表和行数，以知识覆盖进行着色"),
    "list-columns": _Operation(on_table=True, help="列出表里的列，以知识覆盖进行着色"),
    "show": _Operation(on_table=True, help="按 rowid 升序渲染整张表"),
}


def _stderr() -> Console:
    return Console(stderr=True, soft_wrap=True, emoji=False, highlight=False)


def _help_text() -> str:
    console = Console(soft_wrap=True, emoji=False, highlight=False)
    with console.capture() as capture:
        console.print(_HELP, end="")
    return capture.get()


def _print_error(console: Console, message: str) -> None:
    console.print(f"[bold]用法:[/] {_USAGE}")
    console.print(Text.assemble(f"{_PROG}: ", ("错误:", "bold red"), f" {message}"))


def _print_hint(console: Console, text: str) -> None:
    console.print()
    console.print(Text(text, style="dim"))


def usage_error(message: str) -> NoReturn:
    """向 stderr 打印用法行与错误，以退出码 2 退出进程。"""
    _print_error(_stderr(), message)
    sys.exit(2)


class _Parser(argparse.ArgumentParser):
    """帮助与错误由本模块书写，argparse 只负责解析、-h 的触发与退出。"""

    def format_help(self) -> str:
        return _help_text()

    def error(self, message: str) -> NoReturn:
        usage_error(message)


def _non_negative(raw: str) -> int:
    if not raw.isdigit():
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}")
    return int(raw)


def parse_args() -> argparse.Namespace:
    """解析命令行。-h 打印帮助后退出；用法错误时经 usage_error 退出。

    db 与 table 为原始输入，未经别名与工作区解析；operation 为操作名，未指定时为 None。
    指定了 db 与操作时，检查操作与是否指定表相符。
    """
    parser = _Parser(prog=_PROG)
    parser.add_argument("db", nargs="?")
    parser.add_argument("table", nargs="?")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("-k", "--kv", dest="form", action="store_const", const="kv")
    form.add_argument("-j", "--json", dest="form", action="store_const", const="json")
    parser.set_defaults(form="table")
    operation = parser.add_mutually_exclusive_group()
    for name in _OPERATIONS:
        operation.add_argument(f"--{name}", dest="operation", action="store_const", const=name)
    parser.add_argument("-l", "--last", type=_non_negative)
    parser.add_argument("-C", "--columns", nargs="?", const="uhd", type=parse_statuses, action="append")
    parser.add_argument("-P", "--fields", nargs="?", const="uhd", type=parse_statuses, action="append")
    parser.add_argument("-n", "--name", action="store_true")
    parser.add_argument("-q", "--no-summary", action="store_true")
    args = parser.parse_args()

    if args.db is not None and args.operation is not None:
        on_table = _OPERATIONS[args.operation].on_table
        if on_table and args.table is None:
            usage_error(f"--{args.operation} 是对表的操作，需要在数据库之后指定表")
        if not on_table and args.table is not None:
            usage_error(f"--{args.operation} 是对数据库的操作，不能指定表: {args.table}")
    return args


def _print_group(console: Console, title: Text, entries: Sequence[tuple[str, list[str]]]) -> None:
    """entries 为 (名称, 别名) 对，DatabaseEntry 与 TableEntry 均满足。"""
    console.print(title)
    if not entries:
        console.print(Text("  (无)", style="dim"))
    for name, aliases in entries:
        line = Text.assemble("  ", name)
        if aliases:
            line.append(f" (别名: {', '.join(aliases)})", style="yellow")
        console.print(line)


def print_databases(catalog: Catalog) -> None:
    """向 stderr 打印用法行与缺少 <db> 的错误，再按工作区、当前文件夹、其他位置的别名分组打印可用的数据库。"""
    console = _stderr()
    _print_error(console, "缺少 <db>")
    console.print()
    if catalog.workspace is not None:
        _print_group(console, Text.assemble("工作区 ", (str(catalog.workspace), "bold pink1"), " 下可用的数据库:", style="bold"), catalog.in_workspace)
        console.print()
    _print_group(console, Text("当前文件夹下可用的数据库:", style="bold"), catalog.in_cwd)
    if catalog.outside:
        console.print()
        console.print(Text("其他位置的别名:", style="bold"))
        for alias in catalog.outside:
            line = Text.assemble("  ", (alias.alias, "yellow"), (f" → {alias.target}", "dim"))
            if not alias.usable:
                line.append(" (未找到)", style="red")
            console.print(line)
    _print_hint(console, f"使用 {_PROG} -h 查看完整帮助。")


def _print_operations(console: Console, subject: str, *, on_table: bool) -> None:
    available = {f"--{name}": operation for name, operation in _OPERATIONS.items() if operation.on_table == on_table}
    width = max(len(flag) for flag in available) + 4
    _print_error(console, "缺少对表的操作" if on_table else "缺少对数据库的操作")
    console.print()
    console.print(Text.assemble((subject, "bold pink1"), " 可用的操作:", style="bold"))
    for flag, operation in available.items():
        console.print(Text.assemble("  ", (flag, "bold"), " " * (width - len(flag)), operation.help))


def print_database_operations(db_name: str, tables: list[TableEntry]) -> None:
    """向 stderr 打印用法行、缺少对数据库的操作的错误、数据库可用的操作，以及库中的表与表别名。"""
    console = _stderr()
    _print_operations(console, db_name, on_table=False)
    console.print()
    _print_group(console, Text("指定了数据库，但未指定表，可用的表:", style="bold"), tables)
    _print_hint(console, f"指定表后可进行对表的操作，使用 {_PROG} -h 查看完整帮助。")


def print_table_operations(table: str) -> None:
    """向 stderr 打印用法行、缺少对表的操作的错误，以及表可用的操作。"""
    console = _stderr()
    _print_operations(console, table, on_table=True)
    _print_hint(console, f"使用 {_PROG} -h 查看完整帮助。")
