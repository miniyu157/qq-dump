"""app.scripts: 主程序调用 cli 脚本的一层——构造命令行、解析 JSON、按需经 sudo 执行。

这里真实启动 cli 脚本，为组件层里代替它们的替身背书: support.records 的字段须与真实输出一致。
判定基准: support.roots 搭出的数据根目录；Android 账号的数据库用文档公式得出的密钥加密，
解密后由 api 读出 support.profile 的期望好友列表，贯通「取密钥 → 解密 → 读取」整条链路。
"""

import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support import roots
from support.cli import captured_stderr
from support.profile import FRIENDS
from support.records import ENTRY_FIELDS, RECORD_FIELDS
from support.requires import default_encoding_represents, known_issue, needs_sqlcipher, posix_only

from api import load_friends
from app import scripts
from app.errors import AppError

__all__ = []

_UID = "u_CCCCCCCCCCCCCCCCCCCCCC"
_FOREIGN = "linux" if sys.platform == "win32" else "windows"
_REASONS = {"no settings.db", "no key", "key mismatch", "permission denied", "not found"}


class _ScriptsCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name).resolve()
        cls.android = cls.base / "android"
        roots.android_account(cls.android, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")
        cls.db_dir = roots.android_sample_account(cls.android, "10", "10003", _UID)

    def setUp(self) -> None:
        temporary = TemporaryDirectory(dir=self.base)
        self.addCleanup(temporary.cleanup)
        self.out = Path(temporary.name) / "out"
        # 脚本进程与本进程须用同一种文本编码。UTF-8 模式若由 -X utf8 开启则不会传给子进程，这里补上环境变量
        if sys.flags.utf8_mode:
            environment = patch.dict(os.environ, {"PYTHONUTF8": "1"})
            environment.start()
            self.addCleanup(environment.stop)

    def get_keys(self, root: Path, *, platform: str, user: str | None = None, qq: str | None = None, key_cache: Path | None = None, as_root: bool = False) -> list[dict[str, object]]:
        with captured_stderr():
            return scripts.get_keys(user, qq, str(root), platform=platform, key_cache=str(key_cache) if key_cache else None, as_root=as_root)

    def decrypt(self, record: dict[str, object], files: list[str], **options: bool) -> bool:
        with captured_stderr():
            return scripts.decrypt(record, str(self.out), "{filename}", files, **{"copy_plain": False, "as_root": False, **options})


class LocateTests(_ScriptsCase):
    def test_platform_and_roots_come_from_the_script(self) -> None:
        self.assertEqual(scripts.locate_data("auto", str(self.android)), scripts.DataLocation("android", [str(self.android)]))
        self.assertEqual(scripts.locate_data(_FOREIGN, None), scripts.DataLocation(_FOREIGN, []))


class GetKeysTests(_ScriptsCase):
    def test_android_records_have_the_fields_the_stand_ins_use(self) -> None:
        records = self.get_keys(self.android, platform="android")
        self.assertEqual([record["uin"] for record in records], ["10001", "10003"])
        self.assertTrue(all(tuple(record) == RECORD_FIELDS for record in records))
        self.assertTrue(all(tuple(entry) == ENTRY_FIELDS for record in records for entry in record["keys"]))

    def test_pc_records_have_the_fields_and_reasons_the_stand_ins_use(self) -> None:
        root = self.base / "foreign"
        if _FOREIGN == "windows":
            roots.windows_account(root, "10001", b"first!KEY@0000#1")
            roots.windows_account(root, "10002", None)
        else:
            roots.linux_accounts(root, [("10001", "u_fakeUID_aaaaaaaaaaaa", "甲", b"first!KEY@0000#1"), ("10002", "u_fakeUID_bbbbbbbbbbbb", "乙", None)])
        records = self.get_keys(root, platform=_FOREIGN)
        self.assertTrue(all(tuple(record) == RECORD_FIELDS for record in records))
        entries = [entry for record in records for entry in record["keys"]]
        self.assertTrue(all(tuple(entry) == ENTRY_FIELDS for entry in entries))
        self.assertEqual({entry["key_note"]["reason"] for entry in entries}, {"no key", "no settings.db"})
        self.assertLessEqual({entry["key_note"]["reason"] for entry in entries}, _REASONS)

    def test_filters_are_passed_on(self) -> None:
        self.assertEqual([record["uin"] for record in self.get_keys(self.android, platform="android", user="10")], ["10003"])
        self.assertEqual([record["uin"] for record in self.get_keys(self.android, platform="android", qq="10001")], ["10001"])
        self.assertEqual(self.get_keys(self.android, platform="android", user="0", qq="10003"), [])

    def test_failing_script_becomes_an_app_error_naming_it(self) -> None:
        root = self.base / "foreign-for-error"
        if not root.exists():
            (roots.windows_account if _FOREIGN == "windows" else lambda base, uin, key: roots.linux_accounts(base, [(uin, "u_fakeUID_aaaaaaaaaaaa", "甲", key)]))(root, "10001", None)
        with self.assertRaises(AppError) as raised:
            self.get_keys(root, platform=_FOREIGN, key_cache=self.base / "absent.json")
        self.assertIn("get_keys.py", str(raised.exception))

    # 已知缺陷: 主程序与脚本之间的管道没有指定编码，随系统默认编码而定。数据根目录的路径里有默认编码表示不了的字符时，
    # 脚本输出记录即失败: 中文 Windows (GBK) 上是 emoji 与生僻字，英文 Windows 上连中文也不行；UTF-8 环境不受影响
    def _assert_listed(self, name: str) -> None:
        root = self.base / name
        roots.android_account(root, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")
        (record,) = self.get_keys(root, platform="android")
        self.assertEqual(Path(record["qq_path"]), root / "data" / "user" / "0" / "com.tencent.mobileqq")

    @known_issue(not default_encoding_represents("数据 根目录"))
    def test_data_root_with_a_chinese_name(self) -> None:
        self._assert_listed("数据 根目录")

    @known_issue(not default_encoding_represents("😀"))
    def test_data_root_with_a_name_outside_the_ansi_code_page(self) -> None:
        self._assert_listed("data 😀")


@needs_sqlcipher
class DecryptTests(_ScriptsCase):
    def _record(self) -> dict[str, object]:
        (record,) = self.get_keys(self.android, platform="android", qq="10003")
        return record

    def test_keys_from_get_keys_decrypt_the_databases_they_were_derived_for(self) -> None:
        self.assertIs(self.decrypt(self._record(), ["profile_info.db"]), True)
        self.assertEqual([friend._asdict() for friend in load_friends(str(self.out / "profile_info.db"))], FRIENDS)

    def test_every_database_is_decrypted_when_no_file_is_named(self) -> None:
        self.assertIs(self.decrypt(self._record(), []), True)
        self.assertEqual(sorted(path.name for path in self.out.iterdir()), sorted([f"gpro_v1-6_{_UID}.db", "nt_msg.db", "profile_info.db"]))

    def test_plain_databases_are_copied_only_on_request(self) -> None:
        self.assertIs(self.decrypt(self._record(), ["plain.db"]), True)
        self.assertFalse((self.out / "plain.db").exists())
        self.assertIs(self.decrypt(self._record(), ["plain.db"], copy_plain=True), True)
        self.assertTrue((self.out / "plain.db").read_bytes().startswith(b"SQLite format 3\x00"))

    def test_failure_is_reported_as_false(self) -> None:
        record = self._record()
        for entry in record["keys"]:
            entry["key"] = "0" * 32
        self.assertIs(self.decrypt(record, ["profile_info.db"]), False)
        self.assertFalse((self.out / "profile_info.db").exists())

    def test_rule_without_a_key_fails_only_the_files_it_covers(self) -> None:
        record = self._record()
        gpro = next(entry for entry in record["keys"] if entry["name"] == "gpro")
        gpro["key"] = None
        self.assertIs(self.decrypt(record, ["profile_info.db"]), True)
        self.assertIs(self.decrypt(record, [f"gpro_v1-6_{_UID}.db"]), False)


@posix_only
class SudoTests(_ScriptsCase):
    """as_root 为真时经 PATH 里的 sudo 执行。这里放一个假 sudo: 记下收到的参数，再原样执行命令。"""

    def setUp(self) -> None:
        super().setUp()
        tools = self.out.parent / "tools"
        tools.mkdir()
        self.log = tools / "sudo.log"
        fake = tools / "sudo"
        fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$FAKE_SUDO_LOG"\nexec "$@"\n', encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        environment = patch.dict(os.environ, {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "FAKE_SUDO_LOG": str(self.log)})
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(scripts.set_sudo_notice, False)

    def test_script_runs_through_sudo_only_when_asked(self) -> None:
        self.get_keys(self.android, platform="android")
        self.assertFalse(self.log.exists())
        records = self.get_keys(self.android, platform="android", as_root=True)
        self.assertEqual([record["uin"] for record in records], ["10001", "10003"])
        argv = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual((argv[0], Path(argv[1]).name), (sys.executable, "get_keys.py"))

    def test_locating_data_never_uses_sudo(self) -> None:
        scripts.locate_data("auto", str(self.android))
        self.assertFalse(self.log.exists())

    def test_notice_names_the_script_but_not_the_keys(self) -> None:
        (record,) = self.get_keys(self.android, platform="android", qq="10003")
        scripts.set_sudo_notice(True)
        with captured_stderr() as captured:
            scripts.decrypt(record, str(self.out), "{filename}", ["absent.db"], copy_plain=False, as_root=True)
        self.assertIn("decrypt_db.py", captured[0])
        for entry in record["keys"]:
            self.assertNotIn(entry["key"], captured[0])


if __name__ == "__main__":
    unittest.main()
