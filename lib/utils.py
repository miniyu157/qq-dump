"""通用工具：依赖检查与风格化消息输出。"""

import importlib.util
import shutil
import sys
from collections.abc import Callable

from lib.ansi import _blue, _good, _reset, _warn

__all__ = ["check_binary_deps", "check_python_deps", "good_log", "info_log", "warn_log"]


def info_log(message: str, file=sys.stderr) -> None:
    print(f"{_blue}i{_reset} {message}", file=file)


def warn_log(message: str, file=sys.stderr) -> None:
    print(f"{_warn}× {message}{_reset}", file=file)


def good_log(message: str, file=sys.stderr) -> None:
    print(f"{_good}●{_reset} {message}{_reset}", file=file)


def check_binary_deps(message: str, deps: list[str], suffix: str = "", log: Callable[[str], None] | None = None) -> None:
    """检查 PATH 中的二进制依赖；缺失时交给 log 输出（缺省 stderr），并以状态码 1 退出。"""
    missing = [name for name in deps if shutil.which(name) is None]
    if missing:
        text = f"{message}{' '.join(missing)}{suffix}"
        if log is None:
            print(text, file=sys.stderr)
        else:
            log(text)
        sys.exit(1)


def check_python_deps(message: str, deps: list[str], suffix: str = "", log: Callable[[str], None] | None = None) -> None:
    """检查当前 Python 的模块依赖；缺失时交给 log 输出（缺省 stderr），并以状态码 1 退出。"""
    missing = [name for name in deps if importlib.util.find_spec(name) is None]
    if missing:
        text = f"{message}{' '.join(missing)}{suffix}"
        if log is None:
            print(text, file=sys.stderr)
        else:
            log(text)
        sys.exit(1)
