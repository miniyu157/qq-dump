"""终端 ANSI 样式，按输出流分为 out 与 err 两组；对应流非 TTY 或无法解释 ANSI 时该组全部为空。

导入时会为 Windows 控制台开启 VT 处理，修改后的控制台模式不在退出时恢复。
"""

import sys

from lib.tui.terminal import enable_ansi

__all__ = ["err", "out"]


class _Styles:
    def __init__(self, stream) -> None:
        on = stream.isatty() and enable_ansi(stream)
        self.TTY = on
        self.RESET = "\033[0m" if on else ""
        self.BOLD = "\033[1m" if on else ""
        self.FAINT = "\033[2m" if on else ""
        self.GRAY = "\033[38;5;245m" if on else ""
        self.ERR = "\033[38;2;255;115;108m" if on else ""
        self.WARN = "\033[38;2;255;226;2m" if on else ""
        self.INFO = "\033[38;2;121;167;252m" if on else ""
        self.PINK = "\033[38;2;255;174;193m" if on else ""
        self.HL = "\033[1;38;2;255;174;193m" if on else ""
        self.GOOD = "\033[38;2;116;251;138m" if on else ""


out = _Styles(sys.stdout)
err = _Styles(sys.stderr)
