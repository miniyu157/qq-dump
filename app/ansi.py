"""终端 ANSI 样式，按输出流分为 out 与 err 两组；对应流非 TTY 时该组全部为空。"""

import sys

__all__ = ["err", "out"]


class _Styles:
    def __init__(self, stream) -> None:
        on = stream.isatty()
        self.TTY = on
        self.RESET = "\033[0m" if on else ""
        self.BOLD = "\033[1m" if on else ""
        self.FAINT = "\033[2m" if on else ""
        self.ERR = "\033[1;38;2;255;115;108m" if on else ""
        self.WARN = "\033[1;38;2;255;226;2m" if on else ""
        self.INFO = "\033[1;38;2;121;167;252m" if on else ""
        self.HL = "\033[1;38;2;255;174;193m" if on else ""
        self.GOOD = "\033[1;38;2;116;251;138m" if on else ""


out = _Styles(sys.stdout)
err = _Styles(sys.stderr)
