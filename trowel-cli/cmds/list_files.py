"""+list-files: 列出工作区与当前文件夹下可用的数据库，以及数据库别名。"""

import os
from pathlib import Path
from typing import NamedTuple

from rich.text import Text

from app.dotfile import Config, resolve_db
from cmds._listing import Entry, print_group, stdout
from db.connection import is_sqlite_file

__all__ = ["run"]


class _OutsideAlias(NamedTuple):
    """目标不在工作区与 CWD 中的别名；usable 表示目标是否为可用的 SQLite 数据库。"""

    alias: str
    target: Path
    usable: bool


class _Listing(NamedTuple):
    """workspace 为 None 时工作区即 CWD，in_workspace 为空，库都在 in_cwd 中。"""

    workspace: Path | None
    in_workspace: list[Entry]
    in_cwd: list[Entry]
    outside: list[_OutsideAlias]


def _same_file(left: Path, right: Path) -> bool:
    """按绝对路径比较，不解析软链接，指向同一文件的不同软链接视为不同条目。"""
    return os.path.abspath(left) == os.path.abspath(right)


def _databases_in(directory: Path) -> list[Path]:
    return [path for path in sorted(directory.iterdir()) if is_sqlite_file(path)]


def _spelling(config: Config, path: Path) -> str:
    """依次尝试省略 .db、文件名与含 / 的路径，取第一个能解析回 path 的写法；别名可能遮蔽前两种。"""
    slashed = str(path) if "/" in str(path) else f"./{path}"
    candidates = [path.name.removesuffix(".db"), path.name, slashed]
    return next(candidate for candidate in candidates if _same_file(resolve_db(config, candidate), path))


def _entry(config: Config, path: Path, targets: dict[str, Path]) -> Entry:
    return Entry(_spelling(config, path), [alias for alias, target in targets.items() if _same_file(target, path)])


def _collect(config: Config) -> _Listing:
    """分别列出工作区与 CWD 下一层的数据库，按文件名排序，再列出目标不在其中的别名。

    以 SQLite 文件头识别数据库，会读取目录中每个文件的开头。
    """
    targets = {alias: resolve_db(config, alias) for alias in config.db_aliases}
    workspace = None if _same_file(config.workspace, Path()) else config.workspace
    workspace_paths = _databases_in(workspace) if workspace is not None else []
    cwd_paths = _databases_in(Path())
    listed = [*workspace_paths, *cwd_paths]
    outside = [_OutsideAlias(alias, target, is_sqlite_file(target)) for alias, target in targets.items() if not any(_same_file(target, path) for path in listed)]
    return _Listing(workspace, [_entry(config, path, targets) for path in workspace_paths], [_entry(config, path, targets) for path in cwd_paths], outside)


def _render(listing: _Listing) -> None:
    """按工作区、当前文件夹、其他位置的别名分组输出。"""
    console = stdout()
    if listing.workspace is not None:
        print_group(console, Text.assemble("工作区 ", (str(listing.workspace), "bold pink1"), " 下可用的数据库:", style="bold"), listing.in_workspace)
        console.print()
    print_group(console, Text("当前文件夹下可用的数据库:", style="bold"), listing.in_cwd)
    if listing.outside:
        console.print()
        console.print(Text("其他位置的别名:", style="bold"))
        for alias in listing.outside:
            line = Text.assemble("  ", (alias.alias, "yellow"), (f" → {alias.target}", "dim"))
            if not alias.usable:
                line.append(" (未找到)", style="red")
            console.print(line)


def run(config: Config) -> None:
    _render(_collect(config))
