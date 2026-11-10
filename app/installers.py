"""依赖补全方式：按当前解释器与平台列出可用的安装命令，并执行选定的方式。

只决定「能怎么装」，不决定「何时装」；缺少依赖时由 app.utils 的 require_* 询问调用。
"""

import importlib
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from app.dependencies import Binary, Module

__all__ = ["Method", "Step", "binary_methods", "command_text", "install", "module_methods"]

_PROJECT_VENV = Path(__file__).resolve().parents[1] / ".venv"
_VENV_PYTHON = _PROJECT_VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


class Step(NamedTuple):
    """一条命令：argv 为实际执行的参数，brief 为省略当前解释器与绝对路径的简写，仅用于菜单显示。"""

    argv: tuple[str, ...]
    brief: str


class Method(NamedTuple):
    """一种补全方式：label 为菜单文字，steps 依次执行，restart 非 None 时完成后改用该解释器重新运行。"""

    label: str
    steps: tuple[Step, ...]
    restart: Path | None


def module_methods(modules: Sequence[Module]) -> list[Method]:
    """列出能把 modules 装进当前解释器 (或项目 .venv) 的方式，按推荐顺序排列；没有可用方式时返回空列表。

    环境被系统包管理器接管 (PEP 668) 时不提供 pip 与 uv；Termux 的 pkg 只在所有模块都有对应包且未处于虚拟环境时提供。
    """
    packages = [module.package for module in modules]
    methods = []
    managed = _externally_managed()
    names = " ".join(packages)
    if not managed and importlib.util.find_spec("pip") is not None:
        methods.append(Method("用 pip 安装到当前 Python", (Step((sys.executable, "-m", "pip", "install", *packages), f"pip install {names}"),), None))
    uv = shutil.which("uv")
    if not managed and uv:
        methods.append(Method("用 uv 安装到当前 Python", (Step(("uv", "pip", "install", "--python", sys.executable, *packages), f"uv pip install {names}"),), None))
    termux_names = [module.termux for module in modules]
    if _on_termux() and sys.prefix == sys.base_prefix and all(termux_names):
        methods.append(Method("用 Termux pkg 安装", (_pkg_step(termux_names),), None))
    venv = _project_venv_method(packages, uv)
    if venv is not None:
        methods.append(venv)
    return methods


def binary_methods(binaries: Sequence[Binary]) -> list[Method]:
    """列出安装 binaries 的方式；目前只支持 Termux 的 pkg，且要求每个二进制都有对应包，其余平台返回空列表。"""
    names = [binary.termux for binary in binaries]
    if _on_termux() and all(names):
        return [Method("用 Termux pkg 安装", (_pkg_step(names),), None)]
    return []


def install(method: Method, *, announce: Callable[[str], None]) -> bool:
    """依次执行 method 的命令，输出直接显示在终端；任一命令失败或无法启动时返回 False。

    每条命令执行前以可复制执行的完整命令文本调用 announce。
    成功且 method.restart 非 None 时不返回：以该解释器和原参数重新运行本程序，并以其退出码退出。
    """
    for step in method.steps:
        announce(_join(step.argv))
        try:
            proc = subprocess.run(step.argv, check=False)
        except OSError:
            return False
        if proc.returncode != 0:
            return False
    importlib.invalidate_caches()
    if method.restart is not None:
        _restart(method.restart)
    return True


def command_text(method: Method, *, brief: bool) -> str:
    """把 method 的命令拼成一行；brief 为假时可复制到当前平台终端执行，为真时为仅供阅读的简写。"""
    return " && ".join(step.brief if brief else _join(step.argv) for step in method.steps)


def _join(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def _pkg_step(names: Sequence[str]) -> Step:
    argv = ("pkg", "install", "-y", *names)
    return Step(argv, _join(argv))


def _on_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION"))


def _externally_managed() -> bool:
    """当前环境是否由系统包管理器接管；虚拟环境内总是可以自行安装。"""
    if sys.prefix != sys.base_prefix:
        return False
    return Path(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED").exists()


def _project_venv_method(packages: list[str], uv: str | None) -> Method | None:
    """安装到项目 .venv 并重新运行；已在其中运行或无法创建时返回 None。"""
    if Path(sys.prefix).resolve() == _PROJECT_VENV.resolve():
        return None

    venv_python = str(_VENV_PYTHON)
    names = " ".join(packages)
    steps = []
    if _VENV_PYTHON.exists():
        label = "安装到项目 .venv 并重新运行"
    elif uv:
        label = "创建项目 .venv，安装后重新运行"
        steps.append(Step(("uv", "venv", "--python", sys.executable, str(_PROJECT_VENV)), "uv venv .venv"))
    elif importlib.util.find_spec("venv") is not None and importlib.util.find_spec("ensurepip") is not None:
        label = "创建项目 .venv，安装后重新运行"
        steps.append(Step((sys.executable, "-m", "venv", str(_PROJECT_VENV)), "python -m venv .venv"))
    else:
        return None
    # uv 创建的虚拟环境不含 pip，有 uv 时统一由 uv 安装；标签已说明安装到 .venv，简写不再重复解释器
    if uv:
        steps.append(Step(("uv", "pip", "install", "--python", venv_python, *packages), f"uv pip install {names}"))
    else:
        steps.append(Step((venv_python, "-m", "pip", "install", *packages), f"pip install {names}"))
    return Method(label, tuple(steps), _VENV_PYTHON)


def _restart(interpreter: Path) -> None:
    """以 interpreter 和原参数重新运行本程序并退出；Windows 的 execv 不等待新进程，改为子进程运行后转发退出码。"""
    argv = [str(interpreter), *sys.argv]
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == "win32":
        sys.exit(subprocess.run(argv, check=False).returncode)
    os.execv(argv[0], argv)
