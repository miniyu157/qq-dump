"""判断并以只读方式打开 SQLite 数据库文件。"""

import sqlite3
from pathlib import Path

__all__ = ["is_sqlite_file", "open_readonly"]

_SQLITE_MAGIC = b"SQLite format 3\x00"


def is_sqlite_file(path: Path) -> bool:
    """文件存在且以 SQLite 文件头开始。未解密的 NTQQ 库不满足。"""
    if not path.is_file():
        return False
    with path.open("rb") as file:
        return file.read(len(_SQLITE_MAGIC)) == _SQLITE_MAGIC


def open_readonly(path: Path) -> sqlite3.Connection:
    """以只读模式打开。调用前先用 is_sqlite_file 检查，否则错误要到首次查询时才出现。"""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
