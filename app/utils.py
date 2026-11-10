"""通用工具：依赖检查与风格化消息输出，消息均写到 stderr。

缺少依赖且有可用补全方式时，交互终端中询问是否补全，非交互时给出可执行的命令。
"""

import importlib.util
import shutil
import sys
from collections.abc import Callable, Sequence

from app.ansi import err
from app.dependencies import Binary, Module
from app.installers import Method, binary_methods, command_text, install, module_methods

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
    """PATH 中缺少任一二进制且未能补全时输出警告并以状态码 1 退出；purpose 为需要这些依赖的功能。

    Termux 上可询问用 pkg 安装，其余平台只提示缺少的名字；会读取 stdin。
    """
    missing = [binary for binary in binaries if not binary_found(binary)]
    if missing and not _offer_install(f"{purpose}需要以下二进制依赖: {' '.join(binary.name for binary in missing)}", binary_methods(missing), lambda: all(map(binary_found, missing)), required=True, context=()):
        sys.exit(1)


def prefer_binaries(purpose: str, binaries: Sequence[Binary]) -> bool:
    """PATH 中缺少任一二进制时输出提示，不退出；返回补全后是否齐全。purpose 为需要这些依赖的功能。

    Termux 上可询问用 pkg 安装；会读取 stdin。
    """
    missing = [binary for binary in binaries if not binary_found(binary)]
    return not missing or _offer_install(f"{purpose}需要以下二进制依赖: {' '.join(binary.name for binary in missing)}", binary_methods(missing), lambda: all(map(binary_found, missing)), required=False, context=())


def require_modules(purpose: str, modules: Sequence[Module]) -> None:
    """当前 Python 缺少任一模块且未能补全时输出警告并以状态码 1 退出；提示使用 pip 包名。purpose 为需要这些依赖的功能。

    可询问用 pip、uv、Termux pkg 或项目 .venv 补全；选择 .venv 时安装后以新解释器重新运行本程序。会读取 stdin。
    """
    missing = [module for module in modules if not module_found(module)]
    if missing and not _offer_install(f"{purpose}需要以下 Python 依赖: {' '.join(module.package for module in missing)}", module_methods(missing), lambda: all(map(module_found, missing)), required=True, context=(_python_line(),)):
        sys.exit(1)


def binary_found(binary: Binary) -> bool:
    """PATH 中是否有该二进制。"""
    return shutil.which(binary.name) is not None


def module_found(module: Module) -> bool:
    """当前 Python 能否找到该模块的导入名。"""
    return importlib.util.find_spec(module.module) is not None


def _python_line() -> str:
    version = sys.version_info
    return f"当前 Python: {version.major}.{version.minor} {err.FAINT}({sys.executable}){err.RESET}"


def _offer_install(message: str, methods: list[Method], satisfied: Callable[[], bool], *, required: bool, context: Sequence[str]) -> bool:
    """报告缺少的依赖，有补全方式时在交互终端中询问；返回补全后 satisfied 是否成立。

    交互菜单显示简写命令，context 为标题中补充的说明行，执行时先输出完整命令；
    非交互时列出各方式可直接复制执行的完整命令。required 决定提示用警告还是普通提示。
    """
    from lib.tui.choose import ChoiceCancelled, choose

    (warn_log if required else info_log)(message)
    if not methods:
        return False
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        for method in methods:
            info_log(f"{method.label}: {err.HL}{command_text(method, brief=False)}{err.RESET}")
        return False

    options = [f"{method.label}  {err.FAINT}{command_text(method, brief=True)}{err.RESET}" for method in methods]
    try:
        index = choose([*options, "暂不补全"], title="\n".join(("选择补全方式:", *context)))
    except (ChoiceCancelled, EOFError):
        index = len(methods)
    if index == len(methods):
        cancel_log("未补全依赖")
        return False
    # 安装命令成功不代表能找到，例如 pip 装到了其他位置，补全后重新检查
    if not install(methods[index], announce=lambda command: info_log(f"执行: {err.HL}{command}{err.RESET}")) or not satisfied():
        warn_log("补全失败")
        return False
    good_log("已补全依赖")
    return True
