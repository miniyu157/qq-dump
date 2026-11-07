"""名称连同指向它的别名的分组列表，list_files 与 preview_tables 共用；输出到 stdout，stdout 不是终端时不着色。"""

from typing import NamedTuple

from rich.console import Console
from rich.text import Text

__all__ = ["Entry", "print_group", "stdout"]


class Entry(NamedTuple):
    """name 为可直接在命令行中输入的写法。"""

    name: str
    aliases: list[str]


def stdout() -> Console:
    return Console(soft_wrap=True, emoji=False, highlight=False)


def print_group(console: Console, title: Text, entries: list[Entry]) -> None:
    console.print(title)
    if not entries:
        console.print(Text("  (无)", style="dim"))
    for entry in entries:
        line = Text.assemble("  ", entry.name)
        if entry.aliases:
            line.append(f" (别名: {', '.join(entry.aliases)})", style="yellow")
        console.print(line)
