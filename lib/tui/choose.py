"""终端选择：交互式方向键或编号输入，返回选中项的下标。"""

import os
import re
import select
import sys
import termios
import tty
from collections.abc import Sequence

__all__ = ["ChoiceCancelled", "choose"]

_pink = "\033[38;2;255;174;193m"

# 选项与提示之间保留的空行数
_HINT_GAP = 2

# 去除标题原有的 SGR，压暗时统一使用 faint
_SGR = re.compile(r"\x1b\[[0-9;]*m")


class ChoiceCancelled(ValueError):
    """按 Esc 取消选择；继承 ValueError，只捕获 ValueError 的调用方无需改动"""


def choose(options: Sequence[str], file=None, *, title: str = "", divider: bool = True) -> int:
    """输出标题与选项并读取选择，返回选中项的下标；file 缺省为 stderr。

    title 按行原样输出在选项上方；选择完成后标题与选项一起压暗。
    divider 为真时，在选择完成后输出一条终端宽度的横线。
    非法输入抛 ValueError，Esc 取消抛其子类 ChoiceCancelled，EOF 与 Ctrl-C 原样抛出；
    异常抛出时终端状态已恢复，调用方可直接输出提示。
    """
    if not options:
        raise ValueError("选项不能为空")

    if file is None:
        file = sys.stderr
    isatty = getattr(file, "isatty", None)
    output_is_tty = isatty is not None and isatty()
    title_lines = _split_title(title)
    if sys.stdin.isatty() and output_is_tty:
        index = _choose_interactive(options, file, title_lines)
    else:
        _draw_title(title_lines, file)
        for number, label in enumerate(options, 1):
            print(f"  {number}. {label}", file=file)
        answer = input()
        try:
            index = int(answer) - 1
        except ValueError:
            raise ValueError(f"未知选项: {answer!r}") from None
        if not 0 <= index < len(options):
            raise ValueError(f"未知选项: {answer!r}")

    if divider:
        line = "─" * _divider_width(file)
        if output_is_tty:
            line = f"\x1b[38;5;245m{line}\x1b[0m"
        print(line, file=file)
    return index


def _split_title(title: str) -> list[str]:
    """把标题块拆成逐行列表；末尾换行不产生额外空行。"""
    if not title:
        return []
    lines = title.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _draw_title(lines: Sequence[str], file, *, dim: bool = False) -> None:
    """逐行输出标题；dim 为真时去掉原有 SGR 并整体使用 faint。"""
    for line in lines:
        if dim:
            file.write(f"\x1b[2K\r\x1b[2m{_SGR.sub('', line)}\x1b[0m\n")
        else:
            file.write(f"{line}\n")
    file.flush()


def _divider_width(file) -> int:
    """取输出端的终端宽度；不可用时按 80 列处理。"""
    try:
        columns = os.get_terminal_size(file.fileno()).columns
    except (AttributeError, OSError, ValueError):
        columns = 80
    return max(1, columns)


def _choose_interactive(options: Sequence[str], file, title_lines: Sequence[str]) -> int:
    """方向键移动高亮，Enter 确认；其余按键忽略。"""
    fd = sys.stdin.fileno()
    settings = termios.tcgetattr(fd)
    index = 0
    hint_drawn = False
    selected = False
    try:
        tty.setcbreak(fd)
        file.write("\x1b[?25l")
        _draw_title(title_lines, file)
        _draw_options(options, file, index)
        _draw_hint(file)
        hint_drawn = True
        while True:
            key = _read_key(fd)

            if key in (b"\r", b"\n"):
                up = len(title_lines) + len(options) + _HINT_GAP
                file.write(f"\x1b[{up}A")
                _draw_title(title_lines, file, dim=True)
                _draw_options(options, file, index, dim=True)
                file.write("\x1b[0J")
                selected = True
                return index

            if key in (b"", b"\x04"):
                raise EOFError

            if key == b"\x1b":
                raise ChoiceCancelled("用户取消选择")

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
            # 提示行位于首选项下方 len(options) + _HINT_GAP 行
            file.write(f"\x1b[{len(options) + _HINT_GAP}A")
            _draw_options(options, file, index)
            _draw_hint(file)
    finally:
        # 取消或中断时清除选项下方的空行与提示行；选中时已在返回前压暗选项并清除提示
        if hint_drawn and not selected:
            file.write(f"\x1b[{_HINT_GAP}A\r\x1b[0J")
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


def _draw_options(options: Sequence[str], file, index: int, *, dim: bool = False) -> None:
    """逐行重绘选项；dim 为真时整体使用 faint，不显示粉色高亮。"""
    for i, label in enumerate(options):
        mark = "❯ " if i == index else "  "
        style = "\x1b[2m" if dim else (_pink if i == index else "")
        file.write(f"\x1b[2K\r{style}{mark}{label}\x1b[0m\n")
    file.flush()


def _draw_hint(file) -> None:
    """空出 _HINT_GAP 行后输出提示，行尾不换行。"""
    file.write("\n" * _HINT_GAP + "\x1b[2m←↓↑→ navigate • enter submit\x1b[0m")
    file.flush()
