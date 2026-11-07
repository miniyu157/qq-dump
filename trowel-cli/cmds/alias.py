"""+alias: 查看与管理 .trowel 中的数据库别名与表别名。

只改写 CWD 下的 .trowel；同名环境变量优先，被它遮蔽时向 stderr 提示。不扫描工作区与 CWD，只读取数据库别名的目标。
"""

import argparse

from rich.console import Console
from rich.text import Text

from app.dotfile import AliasKind, Config, alias_key, file_entries, locate_db, update_file
from app.usage import usage_error
from cmds._listing import stdout
from db.connection import is_sqlite_file

__all__ = ["run"]

_TITLES: dict[AliasKind, str] = {"db": "数据库别名:", "table": "表别名:"}


def _target_text(config: Config, kind: AliasKind, target: str) -> Text:
    """数据库别名的目标在工作区中解析时附上实际路径，并校验是否为 SQLite 数据库；表别名对所有数据库生效，无从校验。"""
    text = Text(f" → {target}")
    if kind == "db":
        path = locate_db(config, target)
        if str(path) != target:
            text.append(f"  {path}", style="dim")
        if not is_sqlite_file(path):
            text.append(" (未找到)", style="red")
    return text


def _list(config: Config) -> None:
    console = stdout()
    for index, (kind, aliases) in enumerate((("db", config.db_aliases), ("table", config.table_aliases))):
        if index:
            console.print()
        console.print(Text(_TITLES[kind], style="bold"))
        if not aliases:
            console.print(Text("  (无)", style="dim"))
        for alias, target in aliases.items():
            line = Text.assemble("  ", (alias, "yellow"), _target_text(config, kind, target))
            if alias_key(kind, alias) in config.environment_keys:
                line.append(" (环境变量)", style="dim")
            console.print(line)


def _warn_shadowed(config: Config, kind: AliasKind, aliases: list[str]) -> None:
    console = Console(stderr=True, soft_wrap=True, emoji=False, highlight=False)
    for key in (alias_key(kind, alias) for alias in aliases):
        if key in config.environment_keys:
            console.print(Text(f"{key} 同时在环境变量中定义，环境变量优先。", style="yellow"))


def _add(config: Config, kind: AliasKind, pairs: dict[str, str]) -> None:
    """全部目标通过校验后才写入；数据库别名的目标须为 SQLite 数据库。"""
    if kind == "db":
        for alias, target in pairs.items():
            if not is_sqlite_file(path := locate_db(config, target)):
                usage_error(f"别名 {alias} 的目标不是 SQLite 数据库文件: {path}")
    previous = file_entries()
    update_file({alias_key(kind, alias): target for alias, target in pairs.items()})
    console = stdout()
    for alias, target in pairs.items():
        old = previous.get(alias_key(kind, alias))
        line = Text.assemble("已添加: " if old is None else "已更新: ", (alias, "yellow"), _target_text(config, kind, target))
        if old not in (None, target):
            line.append(f" (原为 {old})", style="dim")
        console.print(line)
    _warn_shadowed(config, kind, list(pairs))


def _delete(config: Config, kind: AliasKind, aliases: list[str]) -> None:
    """任一别名不在 .trowel 中时都不删除。"""
    previous = file_entries()
    for alias in aliases:
        key = alias_key(kind, alias)
        if key in previous:
            continue
        usage_error(f"{key} 只在环境变量中定义，无法从 .trowel 删除" if key in config.environment_keys else f"别名不存在: {alias}")
    update_file(dict.fromkeys((alias_key(kind, alias) for alias in aliases), None))
    console = stdout()
    for alias in aliases:
        console.print(Text.assemble("已删除: ", (alias, "yellow"), (f" (原为 {previous[alias_key(kind, alias)]})", "dim")))
    _warn_shadowed(config, kind, aliases)


def run(config: Config, args: argparse.Namespace) -> None:
    if args.command == "ls":
        _list(config)
        return
    kind, action = args.command.split("-")
    if action == "add":
        _add(config, kind, dict(args.pairs))
    else:
        _delete(config, kind, list(dict.fromkeys(args.aliases)))
