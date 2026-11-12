"""以子进程运行项目的脚本、主程序与启动器，返回退出码与两路输出。

子进程的环境去掉全部 QQDUMP_* 变量，使结果不受开发者本机配置影响；输出统一按 UTF-8 解码。
主程序一律带 -E 运行，不读仓库根目录的 .env。
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, NamedTuple

from support import REPO

__all__ = ["Result", "captured_stderr", "child_env", "run", "run_main", "run_script"]


class Result(NamedTuple):
    code: int
    out: str
    err: str

    def json(self) -> Any:
        """把 stdout 解析为 JSON；stdout 混入其他内容时抛 ValueError。"""
        return json.loads(self.out)


def child_env(**overrides: str | None) -> dict[str, str]:
    """子进程环境: 当前环境去掉 QQDUMP_* 并开启 UTF-8 模式；overrides 的值为 None 表示删去该变量。"""
    env = {name: value for name, value in os.environ.items() if not name.startswith("QQDUMP_")}
    env["PYTHONUTF8"] = "1"
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def run(argv: list[str], *, env: dict[str, str] | None = None, cwd: str | None = None, stdin: str | None = None) -> Result:
    """运行 argv 并等待结束；stdin 为 None 时子进程的标准输入是空设备，即非交互。

    输出按 UTF-8 解码，无法解码的字节替换为 U+FFFD，使编码错误表现为断言失败而不是读取线程里的异常。
    """
    done = subprocess.run(argv, input=stdin, stdin=subprocess.DEVNULL if stdin is None else None, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or child_env(), cwd=cwd, timeout=300, check=False)
    return Result(done.returncode, done.stdout, done.stderr)


def run_script(name: str, *args: str, env: dict[str, str] | None = None, cwd: str | None = None) -> Result:
    """运行 cli/ 下的脚本，如 run_script("get_keys.py", "-r", root)。"""
    return run([sys.executable, str(REPO / "cli" / name), *args], env=env, cwd=cwd)


def run_main(*args: str, env: dict[str, str] | None = None, cwd: str | None = None, stdin: str | None = None) -> Result:
    """运行主程序 main.py -E <args>。"""
    return run([sys.executable, str(REPO / "main.py"), "-E", *args], env=env, cwd=cwd, stdin=stdin)


@contextmanager
def captured_stderr() -> Iterator[list[str]]:
    """暂时把本进程的 stderr 文件描述符改指到临时文件，退出时把其间的输出作为唯一元素放进产出的列表。

    用于在进程内调用会启动子进程的函数: 子进程继承的是文件描述符，contextlib.redirect_stderr 管不到它们。
    """
    captured: list[str] = []
    sys.stderr.flush()
    saved = os.dup(2)
    with tempfile.TemporaryFile() as sink:
        os.dup2(sink.fileno(), 2)
        try:
            yield captured
        finally:
            sys.stderr.flush()
            os.dup2(saved, 2)
            os.close(saved)
            sink.seek(0)
            captured.append(sink.read().decode("utf-8", errors="replace"))
