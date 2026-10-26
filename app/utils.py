"""通用工具：依赖检查与风格化消息输出，消息均写到 stderr。"""

import importlib.util
import shutil
import sys

from app.ansi import err

__all__ = ["good_log", "info_log", "require_binaries", "require_modules", "warn_log"]


def info_log(message: str) -> None:
    print(f"{err.INFO}i{err.RESET} {message}", file=sys.stderr)


def warn_log(message: str) -> None:
    print(f"{err.WARN}× {message}{err.RESET}", file=sys.stderr)


def good_log(message: str) -> None:
    print(f"{err.GOOD}●{err.RESET} {message}", file=sys.stderr)


def require_binaries(purpose: str, names: list[str]) -> None:
    """PATH 中缺少任一二进制时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。"""
    _exit_if_missing(f"{purpose}需要以下二进制依赖", [name for name in names if shutil.which(name) is None])


def require_modules(purpose: str, names: list[str]) -> None:
    """当前 Python 缺少任一模块时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。"""
    _exit_if_missing(f"{purpose}需要以下 Python 依赖", [name for name in names if importlib.util.find_spec(name) is None])


def _exit_if_missing(message: str, missing: list[str]) -> None:
    if missing:
        warn_log(f"{message}: {' '.join(missing)}")
        sys.exit(1)
