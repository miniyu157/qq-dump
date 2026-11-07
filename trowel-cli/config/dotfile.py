""".trowel 中的工作区与别名，以及据此解析数据库名称。"""

import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

__all__ = ["Config", "load_config", "resolve_db"]

_FILE = Path(".trowel")
_PREFIX = "TROWEL_"
_KEY = re.compile(r"TROWEL_(?:(WORKSPACE)|DB_([A-Za-z0-9_]+)|TABLE_([A-Za-z0-9_]+))")


class Config(NamedTuple):
    """workspace 未设置时为 CWD；别名映射到命令行输入时可用的名称。"""

    workspace: Path
    db_aliases: dict[str, str]
    table_aliases: dict[str, str]


def _file_entries() -> dict[str, str]:
    if not _FILE.is_file():
        return {}
    entries = {}
    for number, raw in enumerate(_FILE.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = (part.strip() for part in line.partition("="))
        if not separator:
            sys.exit(f".trowel 第 {number} 行不是键值对: {line}")
        if not _KEY.fullmatch(key):
            sys.exit(f".trowel 第 {number} 行的键无法识别: {key}")
        entries[key] = value
    return entries


def _environment_entries() -> dict[str, str]:
    entries = {key: value for key, value in os.environ.items() if key.startswith(_PREFIX)}
    for key in entries:
        if not _KEY.fullmatch(key):
            sys.exit(f"环境变量无法识别: {key}")
    return entries


def load_config() -> Config:
    """读取 CWD 下的 .trowel，同名 TROWEL_ 环境变量优先。

    键无法识别、行不是键值对或工作区不是文件夹时退出进程。
    """
    workspace, db_aliases, table_aliases = Path(), {}, {}
    for key, value in (_file_entries() | _environment_entries()).items():
        is_workspace, db_alias, table_alias = _KEY.fullmatch(key).groups()
        if is_workspace:
            workspace = Path(value)
        elif db_alias:
            db_aliases[db_alias] = value
        else:
            table_aliases[table_alias] = value
    if not workspace.is_dir():
        sys.exit(f"工作区不是文件夹: {workspace}")
    return Config(workspace, db_aliases, table_aliases)


def resolve_db(config: Config, name: str) -> Path:
    """先按别名替换；含 / 时为相对 CWD 的路径，否则在工作区查找，原名不存在而补 .db 后存在时取后者。

    不检查结果是否存在，找不到时返回工作区内的原名路径。
    """
    target = config.db_aliases.get(name, name)
    if "/" in target:
        return Path(target)
    exact, suffixed = config.workspace / target, config.workspace / f"{target}.db"
    return suffixed if not exact.exists() and suffixed.exists() else exact
