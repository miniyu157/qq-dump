"""启动器 qqdump (POSIX) 与 qqdump.cmd (Windows): 找到 Python 3.11+ 并把参数与退出码原样交给主程序。

判定基准: 主程序的退出码与输出。
只在启动器所属的系统上运行: Windows 上的 bash 可能是 WSL 的，不能代表 POSIX 环境。
"""

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import REPO
from support.cli import Result, child_env, run
from support.requires import posix_only, windows_only

__all__ = []


class _LauncherContract:
    """两个启动器共同的契约；具体的类给出 launcher 并同时继承 unittest.TestCase。"""

    launcher: tuple[str, ...]

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def launch(self, *args: str, python: str | None = None) -> Result:
        return run([*self.launcher, *args], env=child_env(QQDUMP_PYTHON=python or sys.executable), cwd=str(self.work))

    def test_arguments_reach_the_main_program(self) -> None:
        result = self.launch("-E", "-h")
        self.assertEqual(result.code, 0, result.err)
        self.assertIn("--key-cache", result.out)

    def test_exit_codes_are_passed_through(self) -> None:
        self.assertEqual(self.launch("-E", "friends", "-p", str(self.work / "absent.db")).code, 1)
        self.assertEqual(self.launch("-E", "no-such-command").code, 2)

    def test_unusable_qqdump_python_is_reported(self) -> None:
        # 指定了 QQDUMP_PYTHON 就只用它，不再退回其他解释器
        result = self.launch("-E", "-h", python=str(self.work / "no-such-python"))
        self.assertEqual((result.code, result.out), (1, ""))
        self.assertIn("QQDUMP_PYTHON", result.err)


@posix_only
class PosixLauncherTests(_LauncherContract, unittest.TestCase):
    launcher = ("bash", str(REPO / "qqdump"))

    def test_launcher_runs_directly_from_another_directory(self) -> None:
        self.assertTrue(os.access(REPO / "qqdump", os.X_OK), "qqdump 缺少可执行权限")
        result = run([str(REPO / "qqdump"), "-E", "-h"], env=child_env(QQDUMP_PYTHON=sys.executable), cwd=str(self.work))
        self.assertEqual(result.code, 0, result.err)


@windows_only
class WindowsLauncherTests(_LauncherContract, unittest.TestCase):
    launcher = ("cmd.exe", "/d", "/c", str(REPO / "qqdump.cmd"))

    def test_launcher_is_plain_ascii_with_crlf_line_ends(self) -> None:
        # cmd 按控制台代码页解析批处理，非 ASCII 字符或 LF 行尾会让跳转标签失效
        data = (REPO / "qqdump.cmd").read_bytes()
        self.assertTrue(data.isascii())
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
