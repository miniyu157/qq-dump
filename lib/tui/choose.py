"""终端单选与多选：交互式分页选择或编号输入，返回选中项的下标。"""

import re
import sys
import termios
import tty
from collections.abc import Sequence

from lib.tui.terminal import PINK, ChoiceCancelled, divider_line, hint, read_key, split_title, strip_styles, terminal_width, truncate

__all__ = ["ChoiceCancelled", "choose", "choose_many"]

# 列表下方的空行总数；多页时在页码前后各分配一行
_HINT_GAP = 2


def choose(options: Sequence[str], file=None, *, title: str = "", divider: bool = True, height: int = 10, initial: int = 0) -> int:
    """输出单选菜单并从 stdin 读取选择，返回从 0 开始的下标；默认输出到 stderr。

    height 为每页项数，initial 为交互模式的初始光标；交互行超宽时截断，窗口缩放不受支持。
    确认后保留并压暗标题与当前页，divider 控制是否追加终端宽度的分隔线；
    取消、Esc 或 Ctrl-C 后保留标题与当前页，仅清除页码与提示区。
    非 TTY 时列出全部选项，只接受一次编号输入，不使用 initial 作为空输入默认值。
    参数或输入无效抛 ValueError，Esc 抛 ChoiceCancelled，EOF 与 Ctrl-C 原样传播；
    交互结束时恢复终端状态。
    """
    return _choose(options, file, title=title, divider=divider, height=height, initial=initial, selected=(), multiple=False)[0]


def choose_many(options: Sequence[str], file=None, *, title: str = "", divider: bool = True, height: int = 10, initial: int = 0, selected: Sequence[int] = ()) -> list[int]:
    """输出多选菜单并从 stdin 读取选择，按原选项顺序返回下标列表；允许提交空列表。

    空格切换勾选，a 全选或取消全选，Enter 提交；selected 为预选下标，与 initial 独立。
    默认输出到 stderr，分页、保留当前页及 divider 的行为与 choose 相同。
    非 TTY 时列出全部选项，接受空格或逗号分隔的编号，空输入返回空列表；
    不采用预选，重复编号去重，任一编号无效则整次输入失败，不自动重试。
    height 必须为正整数，initial 与 selected 必须为有效下标，选项不能为空。
    参数或输入无效抛 ValueError，Esc 抛 ChoiceCancelled，EOF 与 Ctrl-C 原样传播；
    交互结束时恢复终端状态。交互行超宽时截断，窗口缩放不受支持。
    """
    return _choose(options, file, title=title, divider=divider, height=height, initial=initial, selected=selected, multiple=True)


def _choose(options, file, *, title, divider, height, initial, selected, multiple) -> list[int]:
    if not options:
        raise ValueError("选项不能为空")
    if not isinstance(height, int) or isinstance(height, bool) or height < 1:
        raise ValueError("每页项数必须为正整数")
    for index in (initial, *selected):
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(options):
            raise ValueError(f"选项下标无效: {index!r}")

    if file is None:
        file = sys.stderr
    isatty = getattr(file, "isatty", None)
    output_is_tty = isatty is not None and isatty()
    title_lines = split_title(title)
    if sys.stdin.isatty() and output_is_tty:
        indices = _choose_interactive(options, file, title_lines, height=height, initial=initial, selected=set(selected), multiple=multiple)
    else:
        _draw_title(title_lines, file)
        for number, label in enumerate(options, 1):
            print(f"  {number}. {label}", file=file)
        answer = input()
        tokens = re.split(r"[\s,]+", answer.strip()) if multiple else [answer]
        if multiple and not answer.strip():
            tokens = []
        try:
            indices = sorted({int(token) - 1 for token in tokens})
        except ValueError:
            raise ValueError(f"未知选项: {answer!r}") from None
        if any(not 0 <= index < len(options) for index in indices):
            raise ValueError(f"未知选项: {answer!r}")

    if divider:
        print(divider_line(file, styled=output_is_tty), file=file)
    return indices


def _draw_title(lines: Sequence[str], file, *, dim: bool = False) -> None:
    """逐行输出标题；dim 为真时去掉原有 SGR 并整体使用 faint。"""
    for line in lines:
        if dim:
            file.write(f"\x1b[2K\r\x1b[2m{strip_styles(line)}\x1b[0m\n")
        else:
            file.write(f"{line}\n")
    file.flush()


def _choose_interactive(options, file, title_lines, *, height, initial, selected, multiple) -> list[int]:
    width = terminal_width(file)
    title_lines = [truncate(line, width) for line in title_lines]
    fd = sys.stdin.fileno()
    settings = termios.tcgetattr(fd)
    index = initial
    page_height = min(height, len(options))
    pages = (len(options) + height - 1) // height
    # 光标停在提示行；页码单独占一行，末页也按完整页高绘制。
    up = page_height + (1 if pages > 1 else 0) + _HINT_GAP
    hint_drawn = False
    submitted = False
    try:
        tty.setcbreak(fd)
        file.write("\x1b[?25l")
        _draw_title(title_lines, file)
        _draw_page(options, file, index, selected, height=height, multiple=multiple, width=width)
        hint_drawn = True
        while True:
            key = read_key(fd)

            if key in (b"\r", b"\n"):
                file.write(f"\x1b[{len(title_lines) + up}A")
                _draw_title(title_lines, file, dim=True)
                start = index // height * height
                _draw_options(options[start : start + height], file, index, selected, start=start, multiple=multiple, width=width, dim=True)
                file.write("\x1b[0J")
                submitted = True
                return sorted(selected) if multiple else [index]

            if key in (b"", b"\x04"):
                raise EOFError
            if key == b"\x1b":
                raise ChoiceCancelled("用户取消选择")

            if key in (b"\x1b[A", b"\x1bOA"):
                index = (index - 1) % len(options)
            elif key in (b"\x1b[B", b"\x1bOB"):
                index = (index + 1) % len(options)
            elif key in (b"\x1b[D", b"\x1bOD"):
                index = max(0, index - height)
            elif key in (b"\x1b[C", b"\x1bOC"):
                index = min(len(options) - 1, index + height)
            elif multiple and key == b" ":
                selected.symmetric_difference_update({index})
            elif multiple and key == b"a":
                selected = set() if len(selected) == len(options) else set(range(len(options)))
            else:
                continue
            file.write(f"\x1b[{up}A")
            _draw_page(options, file, index, selected, height=height, multiple=multiple, width=width)
    finally:
        try:
            if hint_drawn and not submitted:
                start = index // height * height
                visible = min(height, len(options) - start)
                file.write(f"\x1b[{up - visible}A\r\x1b[0J")
            file.write("\x1b[?25h")
            file.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, settings)


def _draw_options(options, file, index, selected, *, start, multiple, width, dim=False) -> None:
    for i, label in enumerate(options, start):
        mark = "❯ " if i == index else "  "
        style = "\x1b[2m" if dim else (PINK if i == index else "")
        check = ""
        if multiple:
            symbol = "■" if i in selected else "□"
            check_style = "\x1b[2m" if dim else (f"\x1b[1m{PINK}" if i in selected else "\x1b[90m")
            check = f"\x1b[0m{check_style}{symbol}\x1b[0m{style} "
        line = truncate(f"{style}{mark}{check}{label}\x1b[0m", width)
        file.write(f"\x1b[2K\r{line}\n")
    file.flush()


def _draw_page(options, file, index, selected, *, height, multiple, width) -> None:
    page = index // height
    start = page * height
    visible = options[start : start + height]
    _draw_options(visible, file, index, selected, start=start, multiple=multiple, width=width)
    pages = (len(options) + height - 1) // height
    if pages > 1:
        for _ in range(height - len(visible)):
            file.write("\x1b[2K\r\n")
        line = truncate(f"  页码: {page + 1}/{pages}", width)
        file.write(f"\x1b[2K\r\n\x1b[2K\r\x1b[90m{line}\x1b[0m\n")
    _draw_hint(file, multiple=multiple, width=width, gap=_HINT_GAP - (1 if pages > 1 else 0))


def _draw_hint(file, *, multiple: bool, width: int, gap: int) -> None:
    parts = ["←↓↑→ 移动", "enter 提交"]
    if multiple:
        parts.extend(("space 勾选", "a 全选/取消全选"))
    file.write("\n" * gap + f"\x1b[2K\r{hint(parts, width)}")
    file.flush()
