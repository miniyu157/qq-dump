""".trowel 中的工作区与别名，据此解析数据库名称，以及改写 .trowel 中的别名。"""

import os
import re
from pathlib import Path
from typing import Literal, NamedTuple

__all__ = ["AliasKind", "Config", "ConfigError", "alias_key", "file_entries", "is_alias_name", "load_config", "locate_db", "resolve_db", "update_file"]

_FILE = Path(".trowel")
_PREFIX = "TROWEL_"
_ALIAS = re.compile(r"[A-Za-z0-9_]+")
_KEY = re.compile(rf"TROWEL_(?:(WORKSPACE)|DB_({_ALIAS.pattern})|TABLE_({_ALIAS.pattern}))")

AliasKind = Literal["db", "table"]


class ConfigError(Exception):
    """load_config 遇到配置错误时抛出，参数为完整的错误消息。"""


class Config(NamedTuple):
    """workspace 未设置时为 CWD；别名映射到命令行输入时可用的名称。environment_keys 为取自环境变量的键。"""

    workspace: Path
    db_aliases: dict[str, str]
    table_aliases: dict[str, str]
    environment_keys: frozenset[str]


def is_alias_name(name: str) -> bool:
    """别名只能由字母、数字与下划线组成。"""
    return _ALIAS.fullmatch(name) is not None


def alias_key(kind: AliasKind, alias: str) -> str:
    return f"{_PREFIX}{kind.upper()}_{alias}"


def file_entries() -> dict[str, str]:
    """CWD 下 .trowel 中的键值，不含环境变量；文件不存在时为空。行不是键值对或键无法识别时抛出 ConfigError。"""
    if not _FILE.is_file():
        return {}
    entries = {}
    for number, raw in enumerate(_FILE.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = (part.strip() for part in line.partition("="))
        if not separator:
            raise ConfigError(f".trowel 第 {number} 行不是键值对: {line}")
        if not _KEY.fullmatch(key):
            raise ConfigError(f".trowel 第 {number} 行的键无法识别: {key}")
        entries[key] = value
    return entries


def _environment_entries() -> dict[str, str]:
    entries = {key: value for key, value in os.environ.items() if key.startswith(_PREFIX)}
    for key in entries:
        if not _KEY.fullmatch(key):
            raise ConfigError(f"环境变量无法识别: {key}")
    return entries


def load_config() -> Config:
    """读取 CWD 下的 .trowel，同名 TROWEL_ 环境变量优先。

    键无法识别、行不是键值对或工作区不是文件夹时抛出 ConfigError。
    """
    workspace, db_aliases, table_aliases = Path(), {}, {}
    environment = _environment_entries()
    for key, value in (file_entries() | environment).items():
        is_workspace, db_alias, table_alias = _KEY.fullmatch(key).groups()
        if is_workspace:
            workspace = Path(value)
        elif db_alias:
            db_aliases[db_alias] = value
        else:
            table_aliases[table_alias] = value
    if not workspace.is_dir():
        raise ConfigError(f"工作区不是文件夹: {workspace}")
    return Config(workspace, db_aliases, table_aliases, frozenset(environment))


def locate_db(config: Config, name: str) -> Path:
    """不做别名替换；含 / 时为相对 CWD 的路径，否则在工作区查找，原名不存在而补 .db 后存在时取后者。

    不检查结果是否存在，找不到时返回工作区内的原名路径。
    """
    if "/" in name:
        return Path(name)
    exact, suffixed = config.workspace / name, config.workspace / f"{name}.db"
    return suffixed if not exact.exists() and suffixed.exists() else exact


def resolve_db(config: Config, name: str) -> Path:
    """先按别名替换，再按 locate_db 的规则解析。"""
    return locate_db(config, config.db_aliases.get(name, name))


def update_file(changes: dict[str, str | None]) -> None:
    """改写 CWD 下的 .trowel，文件不存在时新建。

    值为 None 的键移除所有行；其余键改写首次出现的行并移除重复行，未出现时追加到末尾。注释与其他行保持原样。
    """
    lines = _FILE.read_text().splitlines() if _FILE.is_file() else []
    kept, written = [], set()
    for line in lines:
        key = line.partition("=")[0].strip()
        if key not in changes:
            kept.append(line)
        elif changes[key] is not None and key not in written:
            kept.append(f"{key}={changes[key]}")
            written.add(key)
    kept += [f"{key}={value}" for key, value in changes.items() if value is not None and key not in written]
    _FILE.write_text("".join(f"{line}\n" for line in kept))
