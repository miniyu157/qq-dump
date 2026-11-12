"""QQ 目录检查的行为测试；临时数据位于工作区，不访问真实 QQ 私有目录。"""

import io
import os
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.accounts import prepare_access

__all__ = []


class QQDirectoryAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix=".accounts-", dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.users = self.root / "data" / "user"
        # 不依赖运行测试者的身份；目录权限错误在对应文件系统操作处模拟。
        # Windows 没有 os.geteuid, 一并替换后 android 平台的检查在各系统上都能测
        for target in (patch("app.accounts.os.geteuid", return_value=1000, create=True), patch("app.accounts.sys.platform", "linux")):
            target.start()
            self.addCleanup(target.stop)

    def _create_qq(self, user: str) -> Path:
        directory = self.users / user / "com.tencent.mobileqq"
        (directory / "files" / "uid").mkdir(parents=True)
        return directory

    def _assert_missing(self, user: str | None = None) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            prepare_access(str(self.root), user, platform="android", decrypting=False)
        self.assertEqual(raised.exception.code, 1)

    def test_readable_qq_does_not_require_sudo(self) -> None:
        self._create_qq("0")
        self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), False)

    def test_user_without_qq_does_not_force_sudo(self) -> None:
        self._create_qq("0")
        (self.users / "10").mkdir()
        for order in (("0", "10"), ("10", "0")):
            with self.subTest(order=order), patch("app.accounts.Path.iterdir", return_value=[self.users / user for user in order]):
                self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), False)

    def test_multiple_readable_qq_directories_do_not_require_sudo(self) -> None:
        self._create_qq("0")
        self._create_qq("10")
        self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), False)

    def test_missing_users_directory_exits(self) -> None:
        self._assert_missing()

    def test_empty_users_directory_exits(self) -> None:
        self.users.mkdir(parents=True)
        self._assert_missing()

    def test_users_without_qq_exit(self) -> None:
        (self.users / "0").mkdir(parents=True)
        (self.users / "10").mkdir()
        self._assert_missing()

    def test_non_directory_users_path_exits(self) -> None:
        self.users.parent.mkdir(parents=True)
        self.users.touch()
        self._assert_missing()

    def test_selected_missing_user_exits_even_if_another_has_qq(self) -> None:
        self._create_qq("0")
        (self.users / "10").mkdir()
        self._assert_missing("10")

    def test_users_listing_denied_requires_sudo(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.Path.iterdir", side_effect=PermissionError("synthetic permission denial")):
            self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), True)

    def test_selected_user_does_not_require_listing_all_users(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.Path.iterdir", side_effect=PermissionError("synthetic permission denial")):
            self.assertIs(prepare_access(str(self.root), "0", platform="android", decrypting=False), False)

    def test_qq_stat_denied_requires_sudo_in_either_order(self) -> None:
        self._create_qq("0")
        denied = self._create_qq("10")
        original_stat = Path.stat

        def stat(path, *args, **kwargs):
            if path == denied:
                raise PermissionError("synthetic permission denial")
            return original_stat(path, *args, **kwargs)

        with patch("app.accounts.Path.stat", stat):
            for order in (("0", "10"), ("10", "0")):
                with self.subTest(order=order), patch("app.accounts.Path.iterdir", return_value=[self.users / user for user in order]):
                    self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), True)

    def test_selected_qq_stat_denied_is_not_reported_missing(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.Path.stat", side_effect=PermissionError("synthetic permission denial")):
            self.assertIs(prepare_access(str(self.root), "0", platform="android", decrypting=False), True)

    def test_one_unreadable_uid_directory_requires_sudo(self) -> None:
        self._create_qq("0")
        denied = self._create_qq("10") / "files" / "uid"
        original_scandir = os.scandir

        def scandir(path):
            if Path(path) == denied:
                raise PermissionError("synthetic permission denial")
            return original_scandir(path)

        with patch("app.accounts.os.scandir", side_effect=scandir):
            self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), True)
            self.assertIs(prepare_access(str(self.root), "0", platform="android", decrypting=False), False)
            self.assertIs(prepare_access(str(self.root), "10", platform="android", decrypting=False), True)

    def test_missing_uid_directory_in_readable_qq_does_not_require_sudo(self) -> None:
        directory = self.users / "0" / "com.tencent.mobileqq"
        directory.mkdir(parents=True)
        self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), False)

    def test_missing_uid_directory_in_unreadable_qq_requires_sudo(self) -> None:
        directory = self.users / "0" / "com.tencent.mobileqq"
        directory.mkdir(parents=True)
        with patch("app.accounts.os.access", return_value=False):
            self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), True)

    def test_root_does_not_require_sudo_for_existing_qq(self) -> None:
        self._create_qq("0")
        with patch("app.accounts.os.geteuid", return_value=0, create=True):
            self.assertIs(prepare_access(str(self.root), None, platform="android", decrypting=False), False)

    def test_root_still_exits_when_qq_is_missing(self) -> None:
        with patch("app.accounts.os.geteuid", return_value=0, create=True):
            self._assert_missing()


if __name__ == "__main__":
    unittest.main()
