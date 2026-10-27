"""运行配置: 进程环境变量优先，其次读取仓库根目录的 .env。

.env 只解析 KEY=VALUE 行，忽略空行与 # 注释，值两端成对的引号会被移除；不写入 os.environ。
"""

import os
from pathlib import Path

__all__ = ["ENV_FILE", "flag_setting", "path_setting"]

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def flag_setting(name: str) -> bool:
    """取开关配置项；值为 1/true/yes/on (不区分大小写) 时开启，未设置或其余值均为关闭"""
    value = os.environ.get(name)
    if value is None:
        value = _read_env_file().get(name, "")
    return value.strip().lower() in _TRUE_VALUES


def path_setting(name: str) -> str | None:
    """取路径配置项；都未设置或值为空时返回 None。

    环境变量原样返回，相对路径由使用方按当前工作目录解析；
    .env 与仓库绑定，其中的相对路径按仓库根目录解析。
    """
    value = os.environ.get(name)
    if value is not None:
        return value or None
    value = _read_env_file().get(name)
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else ENV_FILE.parent / path)


def _read_env_file() -> dict[str, str]:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values
