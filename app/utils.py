"""通用工具：依赖检查与风格化消息输出，消息均写到 stderr。"""

import importlib.util
import shutil
import sys
from collections.abc import Sequence

from app.ansi import err
from app.dependencies import Binary, Module

__all__ = ["binary_found", "cancel_log", "danger_log", "good_log", "info_log", "module_found", "prefer_binaries", "require_binaries", "require_modules", "warn_log"]


def info_log(message: str) -> None:
    """看起来一点儿也不危险的蓝色提示"""
    print(f"{err.BOLD}{err.INFO}i{err.RESET} {message}", file=sys.stderr)


def cancel_log(message: str) -> None:
    """预期内的用户取消提示，方块与正文整行灰色"""
    print(f"{err.GRAY}■ {message}{err.RESET}", file=sys.stderr)


def warn_log(message: str) -> None:
    """出现错误了显示的警告，其实是黄色的"""
    print(f"{err.BOLD}{err.WARN}× {message}{err.RESET}", file=sys.stderr)


def good_log(message: str) -> None:
    """完全胜利了"""
    print(f"{err.BOLD}{err.GOOD}●{err.RESET} {message}", file=sys.stderr)


def danger_log(message: str) -> None:
    """可能造成数据损失或越权等后果的警告"""
    print(f"{err.BOLD}{err.ERR}† {message}{err.RESET}", file=sys.stderr)


def require_binaries(purpose: str, binaries: Sequence[Binary]) -> None:
    """PATH 中缺少任一二进制时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。"""
    missing = [binary for binary in binaries if not binary_found(binary)]
    if missing:
        warn_log(f"{purpose}需要以下二进制依赖: {' '.join(binary.name for binary in missing)}")
        sys.exit(1)


def prefer_binaries(purpose: str, binaries: Sequence[Binary]) -> bool:
    """PATH 中缺少任一二进制时输出提示，不退出；返回是否齐全。purpose 为需要这些依赖的功能。"""
    missing = [binary for binary in binaries if not binary_found(binary)]
    if missing:
        info_log(f"{purpose}需要以下二进制依赖: {' '.join(binary.name for binary in missing)}")
    return not missing


def require_modules(purpose: str, modules: Sequence[Module]) -> None:
    """当前 Python 缺少任一模块时输出警告并以状态码 1 退出；提示使用 pip 包名。purpose 为需要这些依赖的功能。"""
    missing = [module for module in modules if not module_found(module)]
    if missing:
        warn_log(f"{purpose}需要以下 Python 依赖: {' '.join(module.package for module in missing)}")
        sys.exit(1)


def binary_found(binary: Binary) -> bool:
    """PATH 中是否有该二进制。"""
    return shutil.which(binary.name) is not None


def module_found(module: Module) -> bool:
    """当前 Python 能否找到该模块的导入名。"""
    return importlib.util.find_spec(module.module) is not None
