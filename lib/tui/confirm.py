"""终端确认: 在肯定与否定之间选择，返回布尔值。"""

import sys

from lib.tui.keys import ENTER, EOF, ESCAPE, LEFT, RIGHT, cbreak, read_key
from lib.tui.terminal import PINK, ChoiceCancelled, ansi_supported, divider_line, hint, split_title, strip_styles, terminal_width, truncate

__all__ = ["confirm"]


def confirm(prompt: str, file=None, *, divider: bool = True, default: bool = True, affirmative: str = "是", negative: str = "否") -> bool:
    """输出确认提示并返回是否选择肯定项；默认输出到 stderr。

    交互时 ←→ 或 Tab 切换，Enter 提交，y/n 直接选择；default 决定初始选中项。
    提交后保留并压暗提示与选项，divider 控制是否追加终端宽度的分隔线；
    取消、Esc 或 Ctrl-C 后保留提示与选项，仅清除底部提示区。
    Esc 抛 ChoiceCancelled，Ctrl-C 与 EOF 原样传播；交互行超宽时截断，窗口缩放不受支持。
    非 TTY 或输出端不支持 ANSI 时按纯文本列出 y/n 与标签后读取一行：y/yes 为真，n/no 为假，空行取 default，
    其他内容抛 ValueError。default 或标签无效时抛 ValueError。
    """
    if default is not True and default is not False:
        raise ValueError(f"default 必须是布尔值: {default!r}")
    for name, label in (("affirmative", affirmative), ("negative", negative)):
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{name} 必须是非空字符串")

    if file is None:
        file = sys.stderr
    isatty = getattr(file, "isatty", None)
    output_is_tty = isatty is not None and isatty()
    output_ansi = output_is_tty and ansi_supported(file)
    if sys.stdin.isatty() and output_ansi:
        result = _confirm_interactive(prompt, file, default=default, affirmative=affirmative, negative=negative)
    else:
        result = _confirm_non_interactive(prompt, file, default=default, affirmative=affirmative, negative=negative, styled=output_ansi)
    if divider:
        print(divider_line(file, styled=output_ansi), file=file)
    return result


def _confirm_non_interactive(prompt, file, *, default, affirmative, negative, styled) -> bool:
    # 输出端不解释 ANSI 时去掉调用方传入的样式，否则原样输出
    plain = str if styled else strip_styles
    for line in split_title(prompt):
        print(plain(line), file=file)
    print(f"  y. {plain(affirmative)}{' (默认)' if default else ''}", file=file)
    print(f"  n. {plain(negative)}{'' if default else ' (默认)'}", file=file)
    answer = input()
    normalized = answer.strip().lower()
    if normalized in ("y", "yes"):
        return True
    if normalized in ("n", "no"):
        return False
    if not normalized:
        return default
    raise ValueError(f"未知回答: {answer!r}")


def _confirm_interactive(prompt, file, *, default, affirmative, negative) -> bool:
    width = terminal_width(file)
    lines = [truncate(line, width) for line in split_title(prompt)]
    labels = (affirmative, negative)
    index = 0 if default else 1
    fd = sys.stdin.fileno()
    drawn = False
    submitted = False
    with cbreak(fd):
        try:
            file.write("\x1b[?25l")
            for line in lines:
                file.write(f"{line}\n")
            file.write("\n")
            _draw_choice(file, labels, index, width=width)
            drawn = True
            while True:
                key = read_key(fd)

                if key == ENTER:
                    file.write(f"\x1b[{len(lines) + 3}A")
                    for line in lines:
                        file.write(f"\x1b[2K\r\x1b[2m{strip_styles(line)}\x1b[0m\n")
                    file.write("\x1b[2K\r\n")
                    _draw_choice(file, labels, index, width=width, dim=True)
                    file.write("\x1b[0J")
                    submitted = True
                    return index == 0
                if key == ESCAPE:
                    raise ChoiceCancelled("用户取消选择")
                if key == EOF:
                    raise EOFError
                if key in ("y", "Y"):
                    return True
                if key in ("n", "N"):
                    return False

                if key in ("\t", LEFT, RIGHT):
                    index = 1 - index
                else:
                    continue
                file.write("\x1b[2A")
                _draw_choice(file, labels, index, width=width)
        finally:
            if drawn and not submitted:
                file.write("\x1b[1A\r\x1b[0J")
            file.write("\x1b[?25h")
            file.flush()


def _draw_choice(file, labels, index, *, width: int, dim: bool = False) -> None:
    affirmative, negative = labels
    line = truncate(f"{_option(affirmative, selected=index == 0, dim=dim)}   {_option(negative, selected=index == 1, dim=dim)}", width)
    file.write(f"\x1b[2K\r{line}\n")
    if not dim:
        parts = ("←→/tab 切换", "enter 提交", f"y {affirmative}", f"n {negative}")
        file.write(f"\x1b[2K\r\n\x1b[2K\r{hint(parts, width)}")
    file.flush()


def _option(label: str, *, selected: bool, dim: bool = False) -> str:
    # 二选一用压暗突出当前项；choose 面向长列表，未选中项保持默认色
    if dim:
        mark = "☞ " if selected else "  "
        return f"\x1b[2m{mark}{label}\x1b[0m"
    if selected:
        return f"{PINK}☞\x1b[0m \x1b[1m{PINK}{label}\x1b[0m"
    return f"  \x1b[90m{label}\x1b[0m"
