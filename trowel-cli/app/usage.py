"""命令行解析与全部用法文案: 帮助、用法错误，以及指定了表但未指定操作时的提示。

帮助打印到 stdout，其余打印到 stderr；对应的流不是终端时不着色。
"""

import argparse
import sys
from collections.abc import Callable
from typing import NamedTuple, NoReturn

from rich.console import Console
from rich.text import Text

from cmds.show import parse_statuses

__all__ = ["fail", "parse_args", "print_table_operations", "usage_error"]

_PROG = "trowel"
_USAGE = r"[bold]trowel[/] \[选项] \[<db> \[<table>]] \[+操作] \[操作选项]"

_HELP = r"""[bold]TROWEL -- 开始探索数据库[/]

[bold underline]用法:[/]
  [bold]trowel[/] \[选项] \[工作区操作=[sky_blue2]+list-files[/]] \[操作选项]
  [bold]trowel[/] \[选项] <db> \[数据库操作=[sky_blue2]+preview-tables[/]] \[操作选项]
  [bold]trowel[/] \[选项] <db> <table> <表操作> \[操作选项]

[bold underline]参数:[/]
  [bold]db[/]                        数据库别名、工作区中的名称 (可省略 .db)，
                            或含 / 的路径
  [bold]table[/]                     表或表别名

[bold underline]操作 (工作区):[/]
  [bold dim sky_blue2]+list-files[/]               列出工作区与当前文件夹下可用的数据库，
                            以及数据库别名 [dim](默认)[/]

[bold underline]操作 (数据库):[/]
  [bold dim sky_blue2]+preview-tables[/]           列出库中的表与表别名 [dim](默认)[/]
  [bold pink1]+tables[/]                   查看所有表和行数，以知识覆盖进行着色

[bold underline]操作 (表):[/]
  [bold pink1]+list-columns[/]             列出表里的列，以知识覆盖进行着色
  [bold pink1]+show[/]                     按 rowid 升序渲染整张表
    [bold]-l, --last N[/]            只取末尾 N 行
    [bold]-C, --columns \[uhd][/]     另外显示未定义 (u)、已隐藏 (h)、
                            已丢弃 (d) 的列，省略后缀时全部显示
    [bold]-P, --fields \[uhd][/]      protobuf 字段的显示范围，尚未生效
    [bold]-n, --name[/]              列名后附加 maps 中的语义名称
    [bold]-q, --no-summary[/]        不显示末尾的摘要

[bold underline]操作选项 (+tables, +list-columns, +show):[/]
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


def _non_negative(raw: str) -> int:
    if not raw.isdigit():
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}")
    return int(raw)


def _add_form(parser: argparse.ArgumentParser) -> None:
    form = parser.add_mutually_exclusive_group()
    form.add_argument("-k", "--kv", dest="form", action="store_const", const="kv")
    form.add_argument("-j", "--json", dest="form", action="store_const", const="json")
    parser.set_defaults(form="table")


def _add_show(parser: argparse.ArgumentParser) -> None:
    _add_form(parser)
    parser.add_argument("-l", "--last", type=_non_negative)
    parser.add_argument("-C", "--columns", nargs="?", const="uhd", type=parse_statuses, action="append")
    parser.add_argument("-P", "--fields", nargs="?", const="uhd", type=parse_statuses, action="append")
    parser.add_argument("-n", "--name", action="store_true")
    parser.add_argument("-q", "--no-summary", action="store_true")


class _Level(NamedTuple):
    """default 为未指定操作时执行的操作名，None 表示必须指定操作。"""

    label: str
    default: str | None


# 下标为命令行中位置参数的个数: 未指定 db、只指定 db、指定 db 与 table
_LEVELS = (_Level("工作区", "list-files"), _Level("数据库", "preview-tables"), _Level("表", None))
_POSITIONS = ("数据库", "表")


class _Operation(NamedTuple):
    """level 为 _LEVELS 的下标，命令行的位置参数个数必须与之相等。arguments 向操作自己的解析器声明操作选项，None 表示没有操作选项。"""

    level: int
    help: str
    arguments: Callable[[argparse.ArgumentParser], None] | None


_OPERATIONS = {
    "list-files": _Operation(level=0, help="列出工作区与当前文件夹下可用的数据库，以及数据库别名", arguments=None),
    "preview-tables": _Operation(level=1, help="列出库中的表与表别名", arguments=None),
    "tables": _Operation(level=1, help="查看所有表和行数，以知识覆盖进行着色", arguments=_add_form),
    "list-columns": _Operation(level=2, help="列出表里的列，以知识覆盖进行着色", arguments=_add_form),
    "show": _Operation(level=2, help="按 rowid 升序渲染整张表", arguments=_add_show),
}

_MISSING = {(1, 0): "需要指定数据库", (2, 0): "需要指定数据库与表", (2, 1): "需要在数据库之后指定表"}


def _stderr() -> Console:
    return Console(stderr=True, soft_wrap=True, emoji=False, highlight=False)


def _help_text() -> str:
    console = Console(soft_wrap=True, emoji=False, highlight=False)
    with console.capture() as capture:
        console.print(_HELP, end="")
    return capture.get()


def _print_message(console: Console, message: str) -> None:
    console.print(Text.assemble(f"{_PROG}: ", ("错误:", "bold red"), f" {message}"))


def _print_error(console: Console, message: str) -> None:
    console.print(f"[bold]用法:[/] {_USAGE}")
    _print_message(console, message)


def usage_error(message: str) -> NoReturn:
    """向 stderr 打印用法行与错误，以退出码 2 退出进程。用于命令行输入的错误。"""
    _print_error(_stderr(), message)
    sys.exit(2)


def fail(message: str) -> NoReturn:
    """向 stderr 打印错误，不打印用法行，以退出码 1 退出进程。用于命令行之外的错误，如配置错误。"""
    _print_message(_stderr(), message)
    sys.exit(1)


class _Parser(argparse.ArgumentParser):
    """帮助与错误由本模块书写，argparse 只负责解析、-h 的触发与退出。"""

    def format_help(self) -> str:
        return _help_text()

    def error(self, message: str) -> NoReturn:
        usage_error(message)


def _operation_names(level: int) -> str:
    return ", ".join(f"+{name}" for name, operation in _OPERATIONS.items() if operation.level == level)


def _level_error(name: str, required: int, given: list[str]) -> str:
    """given 为命令行中的位置参数，个数与操作要求的层级不符。"""
    head = f"+{name} 是对{_LEVELS[required].label}的操作"
    if len(given) > required:
        return f"{head}，不能指定{_POSITIONS[required]}: {given[required]}"
    return f"{head}，{_MISSING[required, len(given)]}"


def parse_args() -> argparse.Namespace:
    """解析命令行。-h 打印帮助后退出；用法错误时经 usage_error 退出。

    第一个以 + 开头的 token 为操作，之前的部分由主解析器解析，之后的部分由该操作自己的解析器解析。
    db 与 table 为原始输入，未经别名与工作区解析。operation 为操作名，未指定时取位置参数个数对应层级的默认操作；
    指定了表时没有默认操作，operation 为 None，此时没有操作选项。
    指定了操作时，检查操作的层级与位置参数个数相符。
    """
    argv = sys.argv[1:]
    split = next((index for index, token in enumerate(argv) if token.startswith("+")), len(argv))
    parser = _Parser(prog=_PROG)
    parser.add_argument("db", nargs="?")
    parser.add_argument("table", nargs="?")
    args = parser.parse_args(argv[:split])
    given = [value for value in (args.db, args.table) if value is not None]
    if split == len(argv):
        args.operation = _LEVELS[len(given)].default
        return args

    name, rest = argv[split][1:], argv[split + 1 :]
    if name not in _OPERATIONS:
        usage_error(f"未知的操作: +{name}，对{_LEVELS[len(given)].label}可用的操作: {_operation_names(len(given))}")
    if extra := next((token for token in rest if token.startswith("+")), None):
        usage_error(f"只能指定一个操作: +{name}, {extra}")
    operation = _OPERATIONS[name]
    if operation.level != len(given):
        usage_error(_level_error(name, operation.level, given))
    operation_parser = _Parser(prog=f"{_PROG} +{name}")
    if operation.arguments is not None:
        operation.arguments(operation_parser)
    operation_parser.parse_args(rest, namespace=args)
    args.operation = name
    return args


def print_table_operations(table: str) -> None:
    """向 stderr 打印用法行、缺少对表的操作的错误，以及表可用的操作。"""
    console = _stderr()
    available = {f"+{name}": operation for name, operation in _OPERATIONS.items() if operation.level == 2}
    width = max(len(flag) for flag in available) + 4
    _print_error(console, "缺少对表的操作")
    console.print()
    console.print(Text.assemble("表 ", (table, "bold pink1"), " 可用的操作:", style="bold"))
    for flag, operation in available.items():
        console.print(Text.assemble("  ", (flag, "bold"), " " * (width - len(flag)), operation.help))
    console.print()
    console.print(Text(f"使用 {_PROG} -h 查看完整帮助。", style="dim"))
