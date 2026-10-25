"""终端选择：交互式方向键或编号输入，返回选中项的下标。"""

import os
import select
import sys
import termios
import tty
from collections.abc import Sequence

__all__ = ["choose"]

_pink = "\033[38;2;255;174;193m"


def choose(options: Sequence[str], file=None) -> int:
    """输出选项并读取选择，返回选中项的下标；file 缺省为 stderr。

    非法输入与 Esc 取消抛 ValueError，EOF 与 Ctrl-C 原样抛出。
    """
    if not options:
        raise ValueError("选项不能为空")

    if file is None:
        file = sys.stderr
    isatty = getattr(file, "isatty", None)
    if sys.stdin.isatty() and isatty is not None and isatty():
        return _choose_interactive(options, file)

    for number, label in enumerate(options, 1):
        print(f"  {number}. {label}", file=file)
    answer = input()
    try:
        index = int(answer) - 1
    except ValueError:
        raise ValueError(f"未知选项: {answer!r}") from None
    if not 0 <= index < len(options):
        raise ValueError(f"未知选项: {answer!r}")
    return index


def _choose_interactive(options: Sequence[str], file) -> int:
    """方向键移动高亮，Enter 确认；其余按键忽略。"""
    fd = sys.stdin.fileno()
    settings = termios.tcgetattr(fd)
    index = 0
    try:
        tty.setcbreak(fd)
        file.write("\x1b[?25l")
        _draw_options(options, file, index)
        _draw_hint(file)
        while True:
            key = _read_key(fd)

            if key in (b"\r", b"\n"):
                file.write("\n")
                file.flush()
                return index

            if key in (b"", b"\x04"):
                file.write("\n")
                file.flush()
                raise EOFError

            if key == b"\x1b":
                file.write("\n")
                file.flush()
                raise ValueError("用户取消选择")

            if key in (b"\x1b[A", b"\x1bOA"):
                index = (index - 1) % len(options)
            elif key in (b"\x1b[B", b"\x1bOB"):
                index = (index + 1) % len(options)
            elif key in (b"\x1b[D", b"\x1bOD"):
                index = 0
            elif key in (b"\x1b[C", b"\x1bOC"):
                index = len(options) - 1
            else:
                continue
            # 提示行位于首选项下方 len(options) + 2 行
            file.write(f"\x1b[{len(options) + 2}A")
            _draw_options(options, file, index)
            _draw_hint(file)
    finally:
        file.write("\x1b[?25h")
        file.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, settings)


def _read_key(fd: int) -> bytes:
    """方向键等转义序列一次性读满；单独按 ESC 时返回转义符本身。"""
    data = os.read(fd, 1)
    if data != b"\x1b":
        return data
    seq = data
    while len(seq) < 3:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            break
        seq += os.read(fd, 1)
    return seq


def _draw_options(options: Sequence[str], file, index: int) -> None:
    """光标移至列表下一行行首。"""
    for i, label in enumerate(options):
        if i == index:
            file.write(f"\x1b[2K\r{_pink}❯ {label}\x1b[0m\n")
        else:
            file.write(f"\x1b[2K\r  {label}\n")
    file.flush()


def _draw_hint(file) -> None:
    """提示行后不换行。"""
    file.write("\n\n\x1b[2m←↓↑→ navigate • enter submit\x1b[0m")
    file.flush()
