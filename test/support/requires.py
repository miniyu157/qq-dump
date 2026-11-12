"""测试的前提条件: 探测外部工具与运行环境，提供带原因的跳过装饰器。

工具是否可用以实际运行一次为准；只在 PATH 中找到但无法运行 (例如缺少动态库) 同样算不可用。
"""

import locale
import os
import subprocess
import sys
import tempfile
import unittest
from functools import cache

__all__ = ["default_encoding_represents", "known_issue", "live", "live_big", "needs_openssl", "needs_sqlcipher", "posix_only", "sqlcipher_available", "sqlcipher_opens_non_ascii_paths", "windows_only"]


def _runs(argv: list[str], stdin: bytes) -> bool:
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


@cache
def sqlcipher_available() -> bool:
    """sqlcipher 能否运行并报出加密库版本。"""
    return _runs(["sqlcipher", ":memory:"], b"PRAGMA cipher_version;\n")


@cache
def _openssl_available() -> bool:
    return _runs(["openssl", "version"], b"")


@cache
def sqlcipher_opens_non_ascii_paths() -> bool:
    """sqlcipher 能否打开命令行参数里含非 ASCII 字符的路径。

    Windows 上部分构建按 ANSI 代码页接收参数却当作 UTF-8 解释，此时为假；没有可运行的 sqlcipher 时为真 (无从判断，不标记)。
    """
    if not sqlcipher_available():
        return True
    # 参数被错误解释时 sqlcipher 不报错，而是另建一个文件名乱码的库，因此以目标文件是否出现为准
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "数据库.db")
        subprocess.run(["sqlcipher", path], input=b"CREATE TABLE probe (x);\n", capture_output=True, timeout=30, check=False)
        return os.path.exists(path)


def default_encoding_represents(text: str) -> bool:
    """未指定编码的子进程管道能否表示 text: UTF-8 模式下总能，否则取决于系统的默认编码 (中文 Windows 为 GBK)。"""
    encoding = "utf-8" if sys.flags.utf8_mode else locale.getpreferredencoding(False)
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


def known_issue(present: bool):
    """已登记的缺陷: present 为真时把用例标为预期失败，否则照常要求通过。缺陷的说明写在使用处与 test/README.md。"""
    return unittest.expectedFailure if present else lambda test: test


needs_sqlcipher = unittest.skipUnless(sqlcipher_available(), "需要可运行的 sqlcipher")
needs_openssl = unittest.skipUnless(_openssl_available(), "需要可运行的 openssl")
posix_only = unittest.skipIf(sys.platform == "win32", "仅在 POSIX 系统上有意义")
windows_only = unittest.skipUnless(sys.platform == "win32", "仅在 Windows 上有意义")
live = unittest.skipUnless(os.environ.get("QQDUMP_TEST_LIVE") == "1", "实机层默认跳过: 会读取本机真实的 QQ 数据，设置 QQDUMP_TEST_LIVE=1 后运行")
live_big = unittest.skipUnless(os.environ.get("QQDUMP_TEST_LIVE_BIG") == "1", "大库项默认跳过: 耗时且占用磁盘，设置 QQDUMP_TEST_LIVE_BIG=1 后运行")
