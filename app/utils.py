"""通用工具：依赖检查与风格化消息输出，消息均写到 stderr。"""

import importlib.util
import shutil
import sys

from app.ansi import err

__all__ = ["cancel_log", "danger_log", "good_log", "info_log", "prefer_binaries", "require_binaries", "require_modules", "warn_log"]


def info_log(message: str) -> None:
    """看起来一点儿也不危险的蓝色提示"""
    print(f"{err.INFO}i{err.RESET} {message}", file=sys.stderr)


def cancel_log(message: str) -> None:
    """预期内的用户取消提示，方块与正文整行灰色"""
    print(f"{err.GRAY}■ {message}{err.RESET}", file=sys.stderr)


def warn_log(message: str) -> None:
    """出现错误了显示的警告，其实是黄色的"""
    print(f"{err.WARN}× {message}{err.RESET}", file=sys.stderr)


def good_log(message: str) -> None:
    """完全胜利了"""
    print(f"{err.GOOD}●{err.RESET} {message}", file=sys.stderr)


def danger_log(message: str) -> None:
    """可能造成数据损失或越权等后果的警告"""
    print(f"{err.ERR}† {message}{err.RESET}", file=sys.stderr)


def require_binaries(purpose: str, names: list[str]) -> None:
    """PATH 中缺少任一二进制时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。"""
    _exit_if_missing(f"{purpose}需要以下二进制依赖", _missing_binaries(names))


def prefer_binaries(purpose: str, names: list[str]) -> bool:
    """PATH 中缺少任一二进制时输出提示，不退出；返回是否齐全。purpose 为需要这些依赖的功能。"""
    missing = _missing_binaries(names)
    if missing:
        info_log(f"{purpose}需要以下二进制依赖: {' '.join(missing)}")
    return not missing


def require_modules(purpose: str, names: list[str]) -> None:
    """当前 Python 缺少任一模块时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。"""
    _exit_if_missing(f"{purpose}需要以下 Python 依赖", [name for name in names if importlib.util.find_spec(name) is None])


def _missing_binaries(names: list[str]) -> list[str]:
    return [name for name in names if shutil.which(name) is None]


def _exit_if_missing(message: str, missing: list[str]) -> None:
    if missing:
        warn_log(f"{message}: {' '.join(missing)}")
        sys.exit(1)
