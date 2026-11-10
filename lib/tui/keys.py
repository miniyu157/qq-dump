"""终端按键读取: POSIX 与 Windows 共用同一组按键名称，并管理 cbreak 模式。"""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

__all__ = ["DOWN", "ENTER", "EOF", "ESCAPE", "LEFT", "RIGHT", "UP", "cbreak", "read_key"]

UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
ENTER = "enter"
ESCAPE = "escape"
EOF = "eof"

# POSIX 方向键序列与 Windows 控制台扩展键的次字符
_SEQUENCES = {
    b"\x1b[A": UP,
    b"\x1bOA": UP,
    b"\x1b[B": DOWN,
    b"\x1bOB": DOWN,
    b"\x1b[D": LEFT,
    b"\x1bOD": LEFT,
    b"\x1b[C": RIGHT,
    b"\x1bOC": RIGHT,
}
_WINDOWS_SPECIAL = {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT}
_WINDOWS_CHARS = {"\r": ENTER, "\n": ENTER, "\x1b": ESCAPE, "\x1a": EOF}
_POSIX_CHARS = {b"\r": ENTER, b"\n": ENTER}
# 方向键以外的转义序列与功能键返回空串，调用方按未知按键忽略，不应视为取消
_IGNORED = ""


@contextmanager
def cbreak(fd: int) -> Iterator[None]:
    """进入 cbreak 模式，退出时恢复终端设置；Windows 控制台默认按键即时读取，不做操作。

    用于交互式按键读取，调用前须确认 fd 是终端；POSIX 下正常或异常退出都恢复设置。
    """
    if sys.platform == "win32":
        yield
        return
    settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, settings)


def read_key(fd: int) -> str:
    """读取一个按键，返回 UP、DOWN、LEFT、RIGHT、ENTER、ESCAPE、EOF 或字符本身。

    POSIX 下 fd 为终端文件描述符，转义序列在短暂等待内补齐；Windows 下忽略 fd，直接从控制台读取。
    方向键以外的转义序列与功能键返回空字符串，调用方按未知按键忽略。
    Ctrl-C 抛 KeyboardInterrupt；POSIX 的 Ctrl-D 与 Windows 的 Ctrl-Z 返回 EOF。
    非 ASCII 按键不保证返回可用字符；调用前须确认 fd 是终端。
    """
    if sys.platform == "win32":
        return _read_windows_key()
    return _read_posix_key(fd)


def _read_posix_key(fd: int) -> str:
    data = os.read(fd, 1)
    if data in (b"", b"\x04"):
        return EOF
    if data in _POSIX_CHARS:
        return _POSIX_CHARS[data]
    if data != b"\x1b":
        return data.decode("latin-1")

    second = _read_following(fd)
    if second not in (b"[", b"O"):
        return ESCAPE
    third = _read_following(fd)
    if not third:
        return ESCAPE
    return _SEQUENCES.get(data + second + third, _IGNORED)


def _read_following(fd: int) -> bytes:
    """在短暂等待内读取转义序列的下一个字节，超时返回空字节串。"""
    ready, _, _ = select.select([fd], [], [], 0.05)
    return os.read(fd, 1) if ready else b""


def _read_windows_key() -> str:
    char = msvcrt.getwch()
    if char in ("\x00", "\xe0"):
        return _WINDOWS_SPECIAL.get(msvcrt.getwch(), _IGNORED)
    if char == "\x03":
        raise KeyboardInterrupt
    return _WINDOWS_CHARS.get(char, char)
