"""耗时任务的盲文进度动画：任务执行期间在单行内循环刷新。"""

import os
import sys
import threading
import unicodedata
from typing import Self

__all__ = ["progress"]


def progress(label: str, *, clear: bool | None = None, file=None) -> "_Progress":
    """在任务执行期间展示盲文动画；file 缺省为 stderr。

    clear=None 按是否为终端决定：TTY 清行，非 TTY 保留标签。
    clear=True 始终不留进度行：TTY 清行，非 TTY 不打印标签。
    clear=False 始终保留最终标签。
    """
    return _Progress(label, file, clear)


class _Progress:
    """进度行的生命周期：管理动画线程、光标与行清理。"""

    def __init__(self, label: str, file, clear: bool | None) -> None:
        self._label = label
        self._file = sys.stderr if file is None else file
        self._clear = clear
        self._stop = threading.Event()
        self._thread = None
        self._animated = False
        self._line = label

    def __enter__(self) -> Self:
        if not self._file.isatty():
            if self._clear is not True:
                print(self._label, file=self._file)
            return self

        self._line = _fit(self._label, self._file)
        try:
            self._file.write("\x1b[?25l")
            self._file.flush()
        except OSError:
            return self
        self._animated = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def _animate(self) -> None:
        frames = (
            "⠀⠀", "⠁⠀", "⠁⠀", "⠋⠀", "⠟⠁", "⡞⠍", "⣾⣿", "⣴⣿", "⣐⣼", "⠐⣤", "⠀⢄", "⠀⢀", "⠀⠀",
        )
        index = 0
        while not self._stop.is_set():
            frame = frames[index % len(frames)]
            try:
                self._file.write(f"\r\x1b[K{frame} {self._line}")
                self._file.flush()
            except OSError:
                return
            index += 1
            self._stop.wait(0.1)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
        if self._animated:
            try:
                # 保留标签时补换行，避免后续输出接在进度行末尾
                kept = f"{self._line}\n" if self._clear is False else ""
                self._file.write("\r\x1b[K" + kept + "\x1b[?25h")
                self._file.flush()
            except OSError:
                pass


def _width(text: str) -> int:
    """按终端显示宽度计数，东亚宽字符占两列。"""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _fit(label: str, file) -> str:
    """把标签截断到终端宽度减动画前缀，避免覆盖刷新时换行。"""
    try:
        columns = os.get_terminal_size(file.fileno()).columns
    except (AttributeError, OSError, ValueError):
        columns = 0
    # 部分伪终端未设置窗口尺寸，按 80 列处理
    if columns <= 0:
        columns = 80
    limit = max(1, columns - 3)
    if _width(label) <= limit:
        return label

    kept = []
    width = 0
    for char in label:
        char_width = _width(char)
        if width + char_width > limit - 1:
            break
        kept.append(char)
        width += char_width
    return "".join(kept) + "…"
