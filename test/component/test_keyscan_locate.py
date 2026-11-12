"""cli.keyscan.locate: 识别数据布局、枚举账号、定位默认的数据根目录。

判定基准: 在临时目录里手工搭出的目录结构，以及 README「平台与数据」写明的路径规则。
环境替身: 家目录、/home、SUDO_USER 与 Windows 的 QQ 配置文件都重定向到临时目录，不访问真实的 QQ 数据。
"""

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support.requires import windows_only
from support.roots import account_dir_name

from cli.keyscan import locate

__all__ = []

_QQ_CONFIG = r"C:\Users\Public\Documents\Tencent\QQ\UserDataInfo.ini"


class _Redirected:
    """让 locate 看到的 Path 把若干绝对路径改指到临时目录，其余路径照常；home 为 Path.home() 的返回值。"""

    def __init__(self, home: Path, redirects: dict[str, Path]) -> None:
        self._home = home
        self._redirects = {Path(source).parts: target for source, target in redirects.items()}

    def __call__(self, *parts: str | os.PathLike) -> Path:
        path = Path(*parts)
        for source, target in self._redirects.items():
            if path.parts[:len(source)] == source:
                return target.joinpath(*path.parts[len(source):])
        return path

    def home(self) -> Path:
        return self._home


class DetectLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_numeric_account_directory_means_windows(self) -> None:
        (self.root / "10001" / "nt_qq" / "nt_db").mkdir(parents=True)
        (self.root / "nt_qq" / "global" / "nt_db").mkdir(parents=True)
        self.assertEqual(locate.detect_layout(self.root), "windows")

    def test_hashed_account_directory_means_linux(self) -> None:
        (self.root / account_dir_name("u_fakeUID_aaaaaaaaaaaa") / "nt_db").mkdir(parents=True)
        (self.root / "global" / "nt_db").mkdir(parents=True)
        self.assertEqual(locate.detect_layout(self.root), "linux")

    def test_look_alikes_are_not_recognized(self) -> None:
        # 数字目录下没有 nt_qq/nt_db，哈希位数不足，只有全局目录: 都不算账号目录
        (self.root / "10001" / "nt_db").mkdir(parents=True)
        (self.root / "nt_qq_0a0a" / "nt_db").mkdir(parents=True)
        (self.root / "nt_qq" / "global" / "nt_db").mkdir(parents=True)
        self.assertIsNone(locate.detect_layout(self.root))

    def test_missing_root_is_not_recognized(self) -> None:
        self.assertIsNone(locate.detect_layout(self.root / "absent"))


class AccountPathTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_windows_accounts_are_the_numeric_directories_holding_nt_db(self) -> None:
        for uin in ("20002", "10001"):
            (self.root / uin / "nt_qq" / "nt_db").mkdir(parents=True)
        (self.root / "30003" / "nt_qq").mkdir(parents=True)
        (self.root / "nt_qq" / "nt_db").mkdir(parents=True)
        (self.root / "notes.txt").touch()

        accounts = locate.windows_accounts(self.root)
        self.assertEqual([account.uin for account in accounts], ["10001", "20002"])
        first = accounts[0]
        self.assertEqual((first.uid, Path(first.qq_path), Path(first.db_dir)), ("", self.root / "10001" / "nt_qq", self.root / "10001" / "nt_qq" / "nt_db"))

    def test_windows_accounts_of_an_unreadable_root_are_empty(self) -> None:
        self.assertEqual(locate.windows_accounts(self.root / "absent"), [])

    def test_linux_account_directory_is_derived_from_the_uid(self) -> None:
        uid = "u_fakeUID_aaaaaaaaaaaa"
        self.assertEqual(locate.account_db_dir(self.root, uid), self.root / account_dir_name(uid) / "nt_db")
        self.assertNotEqual(locate.account_db_dir(self.root, uid), locate.account_db_dir(self.root, "u_fakeUID_bbbbbbbbbbbb"))

    def test_login_db_locations(self) -> None:
        self.assertEqual(locate.windows_login_db(self.root), self.root / "nt_qq" / "global" / "nt_db" / "login.db")
        self.assertEqual(locate.linux_login_db_candidates(self.root), [self.root / "global" / "nt_db" / "login.db", self.root / "nt_qq" / "global" / "nt_db" / "login.db"])


class LinuxDefaultRootTests(unittest.TestCase):
    """默认位置是家目录下的 .config/QQ 与 flatpak 的 .var/app/com.qq.QQ/config/QQ，须确有 login.db 才算。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.homes = base / "home"
        self.homes.mkdir()
        # 当前 HOME 模拟 sudo 下的 /root，其下默认没有 QQ 数据
        self.current_home = base / "root"
        self.current_home.mkdir()
        for replacement in (patch.object(locate, "Path", _Redirected(self.current_home, {"/home": self.homes})), patch.object(locate.sys, "platform", "linux")):
            replacement.start()
            self.addCleanup(replacement.stop)

    def _qq(self, home: Path, *, nested: bool = False, flatpak: bool = False) -> Path:
        root = home / (".var/app/com.qq.QQ/config/QQ" if flatpak else ".config/QQ")
        login = root / ("nt_qq/global/nt_db" if nested else "global/nt_db") / "login.db"
        login.parent.mkdir(parents=True)
        login.write_bytes(b"x")
        return root

    def _roots(self, sudo_user: str | None) -> list[Path]:
        env = {name: value for name, value in os.environ.items() if name != "SUDO_USER"}
        if sudo_user is not None:
            env["SUDO_USER"] = sudo_user
        with patch.dict(os.environ, env, clear=True):
            return locate.default_data_roots("linux")

    def test_data_under_the_current_home_is_used(self) -> None:
        expected = self._qq(self.current_home)
        self._qq(self.homes / "alice")
        self.assertEqual(self._roots("alice"), [expected])

    def test_under_sudo_the_invoking_user_comes_before_other_homes(self) -> None:
        self._qq(self.homes / "alice")
        expected = self._qq(self.homes / "bob")
        self.assertEqual(self._roots("bob"), [expected])

    def test_without_sudo_user_the_first_home_with_data_is_used(self) -> None:
        (self.homes / "aaron" / ".config" / "QQ").mkdir(parents=True)
        expected = self._qq(self.homes / "alice")
        self.assertEqual(self._roots(None), [expected])

    def test_login_db_in_the_nested_location_counts(self) -> None:
        expected = self._qq(self.homes / "alice", nested=True)
        self.assertEqual(self._roots("alice"), [expected])

    def test_flatpak_installation_is_found(self) -> None:
        expected = self._qq(self.homes / "alice", flatpak=True)
        self.assertEqual(self._roots("alice"), [expected])

    def test_native_and_flatpak_installations_are_both_listed(self) -> None:
        native = self._qq(self.homes / "alice")
        flatpak = self._qq(self.homes / "alice", flatpak=True)
        self._qq(self.homes / "bob")
        self.assertEqual(self._roots("alice"), [native, flatpak])

    def test_no_data_anywhere(self) -> None:
        self.assertEqual(self._roots("alice"), [])


@windows_only
class WindowsDefaultRootTests(unittest.TestCase):
    """默认位置读自 QQ 的配置文件: UserDataInfo.ini 的 [UserDataSet] UserDataSavePath，其下为 Tencent Files。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / "UserDataInfo.ini"
        replacement = patch.object(locate, "Path", _Redirected(Path(temporary.name), {_QQ_CONFIG: self.config}))
        replacement.start()
        self.addCleanup(replacement.stop)

    def _roots(self, content: str | None) -> list[Path]:
        if content is not None:
            self.config.write_text(content, encoding="utf-8")
        return locate.default_data_roots("windows")

    def test_save_path_gets_tencent_files_appended(self) -> None:
        self.assertEqual(self._roots("[UserDataSet]\nUserDataSavePath=D:\\QQData\n"), [Path(r"D:\QQData\Tencent Files")])

    def test_save_path_already_ending_in_tencent_files(self) -> None:
        self.assertEqual(self._roots("[Other]\nUserDataSavePath=E:\\Wrong\n[userdataset]\nuserdatasavepath = D:\\Docs\\Tencent Files\n"), [Path(r"D:\Docs\Tencent Files")])

    def test_no_usable_configuration(self) -> None:
        for reason, content in {"没有配置文件": None, "没有这一节": "[Other]\nUserDataSavePath=D:\\QQData\n", "取值为空": "[UserDataSet]\nUserDataSavePath=\n"}.items():
            with self.subTest(reason=reason):
                self.config.unlink(missing_ok=True)
                self.assertEqual(self._roots(content), [])


class ForeignLayoutTests(unittest.TestCase):
    def test_another_systems_layout_has_no_default_root_here(self) -> None:
        foreign = "linux" if sys.platform == "win32" else "windows"
        self.assertEqual(locate.default_data_roots(foreign), [])


if __name__ == "__main__":
    unittest.main()
