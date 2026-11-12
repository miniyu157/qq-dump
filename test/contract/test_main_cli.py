"""主程序 main.py 的命令行: 子命令、选项的取值来源、输出与退出码。

判定基准: support.roots 搭出的数据根目录与 support.profile 的期望好友列表；版本号与 git 直接给出的描述比较。
每次运行都带 -E 与指向临时目录的 -k (support.cli.run_main)，不读开发者的环境配置，不写仓库的密钥缓存。
不触发真实的内存扫描: windows 与 linux 的数据只取另一系统的布局。
"""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import REPO, roots
from support.cli import Result, child_env, run, run_main
from support.profile import FRIENDS, OWNER, OWNER_UID, write_profile
from support.requires import needs_sqlcipher

from cli.keyscan.key_cache import read_cached_keys

__all__ = []

_UID = "u_CCCCCCCCCCCCCCCCCCCCCC"
_KEY = "first!KEY@0000#1"
_FOREIGN = "linux" if sys.platform == "win32" else "windows"


def _fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


class _MainCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name).resolve()
        cls.android = cls.base / "android"
        roots.android_account(cls.android, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")
        cls.db_dir = roots.android_sample_account(cls.android, "10", "10003", _UID)
        cls.profile = cls.base / "profile_info.db"
        write_profile(cls.profile)
        # 开发者本机的密钥缓存不应被任何一次运行改动
        cls.repo_cache = REPO / ".cache" / "keys.json"
        cls.repo_cache_before = _fingerprint(cls.repo_cache)

    @classmethod
    def tearDownClass(cls) -> None:
        assert _fingerprint(cls.repo_cache) == cls.repo_cache_before, "仓库的 .cache/keys.json 被测试改动"

    def setUp(self) -> None:
        temporary = TemporaryDirectory(dir=self.base)
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.cache = self.work / "keys.json"

    def main(self, *args: str | Path, env: dict[str, str] | None = None) -> Result:
        """以临时的密钥缓存运行主程序。"""
        return run_main("-k", str(self.cache), *map(str, args), env=env)


class InformationTests(_MainCase):
    def test_help_from_option_and_subcommand_is_the_same_text(self) -> None:
        outputs = [run_main(*args) for args in (("-h",), ("help",), ("key", "-h"))]
        for result in outputs:
            self.assertEqual((result.code, result.err), (0, ""))
            self.assertNotIn("\x1b[", result.out, "输出不是终端时不带样式")
        self.assertEqual(len({result.out for result in outputs}), 1)
        for name in ("key", "db", "web", "friends", "owner", "--key-cache", "QQDUMP_KEY_CACHE", "--platform", "-E, --ignore-env"):
            self.assertIn(name, outputs[0].out)

    def test_version_is_the_git_description(self) -> None:
        git = shutil.which("git")
        describe = subprocess.run([git, "-C", str(REPO), "describe", "--tags", "--always", "--dirty"], capture_output=True, text=True, check=False) if git else None
        date = subprocess.run([git, "-C", str(REPO), "log", "-1", "--format=%cs"], capture_output=True, text=True, check=False) if git else None
        if not (describe and describe.returncode == 0 and date and date.returncode == 0):
            self.skipTest("需要 git 与仓库历史")
        result = run_main("-V")
        self.assertEqual((result.code, result.out), (0, f"{describe.stdout.strip()} ({date.stdout.strip()})\n"))


class ProfileQueryTests(_MainCase):
    def test_friends(self) -> None:
        result = self.main("-p", self.profile, "friends")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json(), FRIENDS)

    def test_owner(self) -> None:
        result = self.main("owner", "-p", self.profile)
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json(), OWNER)

    def test_output_redirected_to_a_file_is_utf8_whatever_the_system_encoding(self) -> None:
        # 回归: Windows 上重定向时曾按 ANSI 代码页编码，中文与 emoji 会崩溃或乱码。这里关掉 UTF-8 模式运行
        result = self.main("-p", self.profile, "friends", env=child_env(PYTHONUTF8=None, PYTHONIOENCODING=None))
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(result.json(), FRIENDS)

    def test_unreadable_database_is_reported_with_exit_code_1(self) -> None:
        for situation, path in {"文件不存在": self.base / "absent.db", "不是数据库": REPO / "README.md"}.items():
            with self.subTest(situation=situation):
                result = self.main("-p", path, "friends", env=child_env(PYTHONUTF8=None, PYTHONIOENCODING=None))
                self.assertEqual((result.code, result.out), (1, ""))
                self.assertIn(path.name, result.err)
                self.assertNotIn("Traceback", result.err)


class KeyTests(_MainCase):
    def test_android_keys(self) -> None:
        result = self.main("-r", self.android, "-u", "10", "key")
        self.assertEqual(result.code, 0, result.err)
        (record,) = result.json()
        self.assertEqual((record["platform"], record["user"], record["uin"]), ("android", "10", "10003"))
        self.assertEqual({entry["name"]: entry["key"] for entry in record["keys"]}, {"gpro": roots.android_gpro_key("10003", roots.GPRO_SALT), "nt": roots.android_nt_key(_UID, roots.RAND)})

    def test_android_keys_are_not_cached(self) -> None:
        self.assertEqual(self.main("-r", self.android, "key").code, 0)
        self.assertFalse(self.cache.exists())

    def test_platform_and_root_can_come_from_the_environment(self) -> None:
        # 不带 -E 运行: 环境变量给出的平台把 Android 目录当作 linux 布局，因缺少 login.db 而失败；带 -E 时按目录结构识别
        env = child_env(QQDUMP_PLATFORM="linux", QQDUMP_ROOT_DIR=str(self.android), QQDUMP_KEY_CACHE=str(self.cache))
        without = run([sys.executable, str(REPO / "main.py"), "key"], env=env)
        self.assertEqual((without.code, without.out), (1, ""))
        self.assertIn("login.db", without.err)
        with_ignore = run([sys.executable, str(REPO / "main.py"), "-E", "-r", str(self.android), "key"], env=env)
        self.assertEqual(with_ignore.code, 0, with_ignore.err)
        self.assertEqual({record["platform"] for record in with_ignore.json()}, {"android"})

    def test_no_account_matches_the_filter(self) -> None:
        result = self.main("-r", self.android, "-a", "99999", "key")
        self.assertEqual((result.code, result.out), (1, ""))


class PcKeyCacheTests(_MainCase):
    """另一系统布局的数据: 密钥只能来自密钥缓存。"""

    def _root(self) -> Path:
        root = self.work / "foreign"
        if _FOREIGN == "windows":
            roots.windows_account(root, "10001", _KEY.encode())
        else:
            roots.linux_accounts(root, [("10001", "u_fakeUID_aaaaaaaaaaaa", "甲", _KEY.encode())])
        return root

    def test_without_a_cache_the_account_is_listed_without_key_and_nothing_is_written(self) -> None:
        result = self.main("-r", self._root(), "key")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual([(record["uin"], record["keys"][0]["key"]) for record in result.json()], [("10001", None)])
        self.assertFalse(self.cache.exists())

    def test_key_from_a_hand_written_cache_is_stored_back_in_full_form_once(self) -> None:
        root = self._root()
        self.cache.write_text(json.dumps([{"platform": _FOREIGN, "uin": "10001", "keys": [{"key": _KEY}]}]), encoding="utf-8")

        first = self.main("-r", root, "key")
        self.assertEqual(first.code, 0, first.err)
        self.assertEqual(first.json()[0]["keys"][0]["key_note"], {"source": "key cache", "kdf": "sha512"})
        stored = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual(stored[-1]["keys"], [{"name": "nt", "pattern": "*.db", "key": _KEY, "hmac_algorithm": "HMAC_SHA1"}])
        self.assertEqual(read_cached_keys(self.cache, platform=_FOREIGN)["10001"][0], _KEY.encode())

        before = self.cache.read_bytes()
        second = self.main("-r", root, "key")
        self.assertEqual(second.code, 0, second.err)
        self.assertEqual(self.cache.read_bytes(), before, "已记入的密钥不再写入")
        self.assertNotIn(str(self.cache), second.err)

    def test_unusable_cache_file_stops_with_exit_code_1(self) -> None:
        self.cache.write_text("# 来源: windows\n10001 first!KEY@0000#1\n", encoding="utf-8")
        result = self.main("-r", self._root(), "key")
        self.assertEqual((result.code, result.out), (1, ""))
        self.assertIn("keys.json", result.err)
        self.assertEqual(self.cache.read_text(encoding="utf-8"), "# 来源: windows\n10001 first!KEY@0000#1\n")


@needs_sqlcipher
class DbTests(_MainCase):
    def _uids(self, path: Path) -> list[str]:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return [uid for (uid,) in conn.execute('SELECT "1000" FROM profile_info_v6 ORDER BY rowid')]
        finally:
            conn.close()

    def test_databases_are_written_under_user_and_uin_by_default(self) -> None:
        out = self.work / "out"
        result = self.main("-r", self.android, "-a", "10003", "-o", out, "db", "profile_info.db", "nt_msg.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(sorted(path.name for path in (out / "10.10003").iterdir()), ["nt_msg.db", "profile_info.db"])
        # 资料表里除好友外还有主人与一行 20001 为空的路人
        self.assertEqual(self._uids(out / "10.10003" / "profile_info.db"), [OWNER_UID, *(friend["uid"] for friend in FRIENDS), "u_stranger_f"])

    def test_decrypted_profile_feeds_the_friend_query(self) -> None:
        out = self.work / "out"
        self.assertEqual(self.main("-r", self.android, "-a", "10003", "-o", out, "db", "profile_info.db").code, 0)
        result = self.main("-p", out / "10.10003" / "profile_info.db", "friends")
        self.assertEqual(result.json(), FRIENDS)

    def test_name_format_fields(self) -> None:
        out = self.work / "out"
        result = self.main("-r", self.android, "-a", "10003", "-o", out, "db", "-f", "{uin}-{uid}/{filename}", "profile_info.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertTrue((out / f"10003-{_UID}" / "profile_info.db").is_file())

    def test_invalid_name_format_stops_before_decrypting(self) -> None:
        out = self.work / "out"
        result = self.main("-r", self.android, "-a", "10003", "-o", out, "db", "-f", "{nonexistent}/{filename}")
        self.assertEqual(result.code, 1)
        self.assertIn("--name-format", result.err)
        self.assertFalse(out.exists())

    def test_failure_of_one_account_makes_the_exit_code_1(self) -> None:
        # 10001 没有任何数据库: 指名的文件不存在
        out = self.work / "out"
        result = self.main("-r", self.android, "-o", out, "db", "profile_info.db")
        self.assertEqual(result.code, 1)
        self.assertTrue((out / "10.10003" / "profile_info.db").is_file())


class ArgumentTests(_MainCase):
    def test_invalid_arguments_exit_with_2(self) -> None:
        for args in (("no-such-command",), ("-P", "macos", "key"), ("key", "--export")):
            with self.subTest(args=args):
                result = run_main(*args)
                self.assertEqual((result.code, result.out), (2, ""))


if __name__ == "__main__":
    unittest.main()
