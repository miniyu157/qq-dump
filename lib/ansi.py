"""终端 ANSI 样式；输出非 TTY 时全部为空。"""

import sys

_tty = sys.stdout.isatty()
_reset = "\033[0m" if _tty else ""
_bold = "\033[1m" if _tty else ""
_faint = "\033[2m" if _tty else ""

_red = "\033[1;38;2;255;115;108m" if _tty else ""
_blue = "\033[1;38;2;121;167;252m" if _tty else ""
_pink = "\033[1;38;2;255;174;193m" if _tty else ""
_yellow = "\033[1;38;2;255;226;2m" if _tty else ""
_gerrn = "\033[1;38;2;116;251;138m" if _tty else ""

_err = _red
_warn = _yellow
_info = _blue
_hl = _pink
_good = _gerrn
