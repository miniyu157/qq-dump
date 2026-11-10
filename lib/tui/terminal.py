"""选择与确认共用的终端能力判断、文本处理与结果类型。"""

import os
import re
import sys
import unicodedata
from collections.abc import Sequence

__all__ = ["PINK", "ChoiceCancelled", "ansi_supported", "divider_line", "enable_ansi", "hint", "split_title", "strip_styles", "terminal_width", "truncate"]

PINK = "\033[38;2;255;174;193m"

_SGR = re.compile(r"\x1b\[[0-9;]*m")


class ChoiceCancelled(ValueError):
    """按 Esc 取消选择；继承 ValueError，只捕获 ValueError 的调用方无需改动"""


def split_title(title: str) -> list[str]:
    """把标题块拆成逐行列表；末尾换行不产生额外空行。"""
    if not title:
        return []
    lines = title.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def terminal_width(file) -> int:
    """取输出端的终端宽度；不可用时按 80 列处理。"""
    try:
        columns = os.get_terminal_size(file.fileno()).columns
    except (AttributeError, OSError, ValueError):
        columns = 80
    return max(1, columns)


def divider_line(file, *, styled: bool) -> str:
    """按输出端宽度生成分隔线；styled 为真时使用 245m。"""
    line = "─" * terminal_width(file)
    return f"\x1b[38;5;245m{line}\x1b[0m" if styled else line


def strip_styles(text: str) -> str:
    """移除文本中的 SGR 序列。"""
    return _SGR.sub("", text)


def truncate(text: str, width: int) -> str:
    """按常见终端列宽截断，保留 SGR；复杂 Emoji 序列不保证精确宽度。"""
    tokens = re.findall(r"\x1b\[[0-9;]*m|.", text)
    widths = [0 if token.startswith("\x1b") or unicodedata.category(token) in ("Mn", "Me", "Cf") else 2 if unicodedata.east_asian_width(token) in ("W", "F") else 1 for token in tokens]
    if sum(widths) <= width:
        return text
    parts = []
    used = 0
    for token, columns in zip(tokens, widths):
        if used + columns > width - 1:
            break
        parts.append(token)
        used += columns
    return "".join(parts) + "…\x1b[0m"


def ansi_supported(file) -> bool:
    """输出流能否解释 ANSI 序列；Windows 控制台未启用 VT 处理时返回 False，其余平台视为支持。"""
    if sys.platform != "win32":
        return True
    return _set_vt_processing(file, enable=False)


def enable_ansi(file) -> bool:
    """让输出流解释 ANSI 序列，返回之后能否解释；其余平台视为支持。

    Windows 控制台未启用 VT 处理时尝试开启，会修改该控制台的输出模式且不在退出时恢复；
    旧版控制台拒绝开启或输出流不是控制台时返回 False。
    """
    if sys.platform != "win32":
        return True
    return _set_vt_processing(file, enable=True)


def _set_vt_processing(file, *, enable: bool) -> bool:
    """读取控制台输出模式，enable 为真且未开启时尝试开启 VT 处理；返回最终是否开启。"""
    import ctypes
    import msvcrt

    vt_processing = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    try:
        handle = ctypes.c_void_p(msvcrt.get_osfhandle(file.fileno()))
    except (AttributeError, OSError, ValueError):
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetConsoleMode.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    kernel32.GetConsoleMode.restype = ctypes.c_int
    kernel32.SetConsoleMode.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.SetConsoleMode.restype = ctypes.c_int
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    if mode.value & vt_processing:
        return True
    return enable and bool(kernel32.SetConsoleMode(handle, mode.value | vt_processing))


def hint(parts: Sequence[str], width: int) -> str:
    """把「按键 说明」对拼成底部提示；按键用 245m，说明与圆点用 90m，超宽截断。"""
    text = " \x1b[90m•\x1b[0m ".join(f"\x1b[38;5;245m{key}\x1b[0m\x1b[90m {description}\x1b[0m" for key, description in (part.split(" ", 1) for part in parts))
    return truncate(text, width)
