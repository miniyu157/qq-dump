"""cli/get_keys.py 的命令行: 判定平台与数据根目录，输出各账号的密钥记录。

判定基准: support.roots 搭出的三种数据根目录；Android 的期望密钥由文档公式用 hashlib 直接算出。
不触发真实的内存扫描: windows 与 linux 的数据只取「全部由缓存命中」「缺少 settings.db」或「另一系统的布局」。
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import qqnt, roots
from support.cli import Result, run_script
from support.records import ENTRY_FIELDS, RECORD_FIELDS

__all__ = []

_KEY_A = "first!KEY@0000#1"
_KEY_B = "second!KEY@000#2"
_UID_A = "u_fakeUID_aaaaaaaaaaaa"
_UID_B = "u_fakeUID_bbbbbbbbbbbb"
# 运行系统对应的布局会去扫描真实进程，另一种布局只读数据目录
_NATIVE = "windows" if sys.platform == "win32" else "linux"
_FOREIGN = "linux" if sys.platform == "win32" else "windows"


class _CliCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name).resolve()

    def get_keys(self, *args: str | Path) -> Result:
        return run_script("get_keys.py", *map(str, args))

    def records(self, *args: str | Path) -> list[dict[str, object]]:
        """运行并要求成功，返回 stdout 中的记录数组。"""
        result = self.get_keys(*args)
        self.assertEqual(result.code, 0, result.err)
        return result.json()


class AndroidTests(_CliCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.root = cls.base / "android"
        # user 0 / 10001: 有账号标记，数据库目录是空的
        roots.android_account(cls.root, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")
        # user 0 / 10002: 库的文件头没有 QQ_NT DB 标记，gpro 的盐值无法识别
        cls.uid_b = "u_BBBBBBBBBBBBBBBBBBBBBB"
        db_dir = roots.android_account(cls.root, "0", "10002", cls.uid_b)
        (db_dir / "nt_msg.db").write_bytes(roots.nt_header(None) + bytes(100))
        (db_dir / f"gpro_v1-6_{cls.uid_b}.db").write_bytes(roots.gpro_header(None))
        # user 10 / 10003: 文件头齐全，另有一个不是数据库的文件
        cls.uid_c = "u_CCCCCCCCCCCCCCCCCCCCCC"
        cls.db_dir_c = roots.android_account(cls.root, "10", "10003", cls.uid_c)
        (cls.db_dir_c / "profile_info.db").write_bytes(roots.nt_header(roots.RAND) + bytes(300))
        (cls.db_dir_c / "nt_msg.db").write_bytes(roots.nt_header(roots.RAND) + bytes(200))
        (cls.db_dir_c / f"gpro_v1-6_{cls.uid_c}.db").write_bytes(roots.gpro_header(roots.GPRO_SALT) + bytes(50))
        (cls.db_dir_c / "readme.txt").write_text("不是数据库", encoding="utf-8")
        # 格式无效的账号标记: 缺少分隔符、uin 为空、uid 为空
        marks = cls.root / "data" / "user" / "0" / "com.tencent.mobileqq" / "files" / "uid"
        for name in ("10004", "###u_EEEEEEEEEEEEEEEEEEEEEE", "10006###"):
            (marks / name).touch()

    def test_accounts_are_listed_by_android_user_and_malformed_marks_are_skipped(self) -> None:
        records = self.records("-r", self.root)
        self.assertEqual([(record["platform"], record["user"], record["uin"]) for record in records], [("android", "0", "10001"), ("android", "0", "10002"), ("android", "10", "10003")])
        self.assertTrue(all(tuple(record) == RECORD_FIELDS for record in records))

    def test_record_locates_the_account(self) -> None:
        record = self.records("-r", self.root, "-a", "10003")[0]
        qq_path = self.root / "data" / "user" / "10" / "com.tencent.mobileqq"
        self.assertEqual((record["uid"], Path(record["qq_path"]), Path(record["db_dir"])), (self.uid_c, qq_path, self.db_dir_c))

    def test_keys_follow_the_documented_formulas(self) -> None:
        gpro, nt = self.records("-r", self.root, "-a", "10003")[0]["keys"]
        self.assertEqual((tuple(gpro), tuple(nt)), (ENTRY_FIELDS, ENTRY_FIELDS))
        self.assertEqual((gpro["name"], gpro["pattern"], gpro["key"], gpro["hmac_algorithm"]), ("gpro", f"gpro_v1-6_{self.uid_c}.db", roots.android_gpro_key("10003", roots.GPRO_SALT), "HMAC_SHA512"))
        self.assertEqual((nt["name"], nt["pattern"], nt["key"], nt["hmac_algorithm"]), ("nt", "*.db", roots.android_nt_key(self.uid_c, roots.RAND), "HMAC_SHA1"))
        self.assertEqual((gpro["key_note"], nt["key_note"]), ({"salt": roots.GPRO_SALT.decode()}, {"rand": roots.RAND}))

    def test_each_file_belongs_to_the_first_rule_matching_it(self) -> None:
        gpro, nt = self.records("-r", self.root, "-a", "10003")[0]["keys"]
        self.assertEqual(gpro["files"], [{"name": f"gpro_v1-6_{self.uid_c}.db", "size": 1024 + 50}])
        self.assertEqual(nt["files"], [{"name": "nt_msg.db", "size": 1024 + 200}, {"name": "profile_info.db", "size": 1024 + 300}])

    def test_header_without_rand_still_yields_an_nt_key(self) -> None:
        gpro, nt = self.records("-r", self.root, "-a", "10002")[0]["keys"]
        self.assertEqual((nt["key"], nt["key_note"]), (roots.android_nt_key(self.uid_b, ""), {"rand": ""}))
        # 盐值识别不出时这一类仍列出，密钥为 null
        self.assertEqual((gpro["key"], gpro["key_note"], [file["name"] for file in gpro["files"]]), (None, {}, [f"gpro_v1-6_{self.uid_b}.db"]))

    def test_account_without_databases_has_no_rules(self) -> None:
        self.assertEqual(self.records("-r", self.root, "-a", "10001")[0]["keys"], [])

    def test_filters(self) -> None:
        cases = {("-u", "10"): ["10003"], ("-u", "0"): ["10001", "10002"], ("-a", "10002"): ["10002"], ("-a", self.uid_c): ["10003"], ("-u", "0", "-a", "10003"): [], ("-a", "99999"): []}
        for options, expected in cases.items():
            with self.subTest(options=options):
                self.assertEqual([record["uin"] for record in self.records("-r", self.root, *options)], expected)

    def test_stdout_is_only_the_json_array(self) -> None:
        result = self.get_keys("-r", self.root)
        self.assertEqual((result.code, result.err), (0, ""))
        self.assertEqual(result.out, json.dumps(result.json(), ensure_ascii=False, indent=2) + "\n")

    def test_key_cache_is_not_consulted_for_android(self) -> None:
        self.assertEqual(self.records("-r", self.root, "-k", self.base / "absent.json"), self.records("-r", self.root))


class LocateTests(_CliCase):
    """--locate 只报告判定的平台与数据根目录候选，不取密钥。"""

    def _locate(self, *args: str | Path) -> dict[str, object]:
        result = self.get_keys("--locate", *args)
        self.assertEqual(result.code, 0, result.err)
        return result.json()

    def _root(self, name: str, marker: str) -> Path:
        root = self.base / name
        (root / marker).mkdir(parents=True, exist_ok=True)
        return root

    def test_platform_is_recognized_from_the_structure_under_the_root(self) -> None:
        markers = {"android": "data/user", "windows": "10001/nt_qq/nt_db", "linux": f"{roots.account_dir_name(_UID_A)}/nt_db"}
        for platform, marker in markers.items():
            with self.subTest(platform=platform):
                root = self._root(f"locate-{platform}", marker)
                self.assertEqual(self._locate("-r", root), {"platform": platform, "roots": [str(root)]})

    def test_unrecognized_root_falls_back_to_the_running_system(self) -> None:
        # 帮助写明的规则: Windows 为 windows，存在 /data/user 为 android，其余为 linux
        expected = "windows" if sys.platform == "win32" else "android" if Path("/data/user").is_dir() else "linux"
        root = self._root("locate-empty", ".")
        self.assertEqual(self._locate("-r", root), {"platform": expected, "roots": [str(root)]})

    def test_explicit_platform_overrides_the_structure(self) -> None:
        root = self._root("locate-explicit", "data/user")
        self.assertEqual(self._locate("-P", "linux", "-r", root)["platform"], "linux")

    def test_layout_of_another_system_has_no_default_root(self) -> None:
        self.assertEqual(self._locate("-P", _FOREIGN), {"platform": _FOREIGN, "roots": []})

    def test_android_defaults_to_the_filesystem_root(self) -> None:
        self.assertEqual(self._locate("-P", "android"), {"platform": "android", "roots": [str(Path("/"))]})

    def test_taking_keys_without_a_root_is_an_error(self) -> None:
        result = self.get_keys("-P", _FOREIGN)
        self.assertNotEqual(result.code, 0)
        self.assertEqual(result.out, "")
        self.assertIn("-r", result.err)


class PcTests(_CliCase):
    """windows 与 linux 的数据: 账号由数据目录枚举，密钥来自 -k 的密钥缓存。"""

    def _build(self, layout: str, name: str, accounts: list[tuple[str, str, str | None]]) -> Path:
        """建一个 layout 布局的数据根目录；accounts 每项为 (uin, uid, 密钥)，密钥为 None 时该账号没有 settings.db。"""
        root = self.base / name
        if layout == "windows":
            for uin, _, key in accounts:
                roots.windows_account(root, uin, key.encode() if key else None)
            roots.write_login_db(root / "nt_qq" / "global" / "nt_db" / "login.db", [(uin, uid, f"昵称{uin}") for uin, uid, _ in accounts])
        else:
            roots.linux_accounts(root, [(uin, uid, f"昵称{uin}", key.encode() if key else None) for uin, uid, key in accounts])
        return root

    def _cache(self, name: str, *entries: tuple[str, str, str]) -> Path:
        """写一份密钥缓存，entries 每项为 (平台, uin, 密钥)。"""
        path = self.base / name
        path.write_text(json.dumps([{"platform": platform, "uin": uin, "keys": [{"key": key}]} for platform, uin, key in entries]), encoding="utf-8")
        return path

    def test_accounts_are_enumerated_from_either_layout_on_any_system(self) -> None:
        for layout in ("windows", "linux"):
            with self.subTest(layout=layout):
                root = self._build(layout, f"enumerate-{layout}", [("10001", _UID_A, _KEY_A), ("10002", _UID_B, _KEY_B)])
                cache = self._cache(f"enumerate-{layout}.json", (layout, "10001", _KEY_A), (layout, "10002", _KEY_B))
                records = self.records("-r", root, "-k", cache)
                self.assertTrue(all(tuple(record) == RECORD_FIELDS for record in records))
                self.assertEqual(sorted((record["platform"], record["user"], record["uin"], record["uid"]) for record in records), [(layout, layout, "10001", _UID_A), (layout, layout, "10002", _UID_B)])
                expected_dir = {"windows": root / "10001" / "nt_qq" / "nt_db", "linux": root / roots.account_dir_name(_UID_A) / "nt_db"}[layout]
                self.assertEqual(Path(next(record["db_dir"] for record in records if record["uin"] == "10001")), expected_dir)

    def test_cached_keys_are_verified_and_reported_with_their_source(self) -> None:
        for layout in ("windows", "linux"):
            with self.subTest(layout=layout):
                root = self._build(layout, f"cached-{layout}", [("10001", _UID_A, _KEY_A), ("10002", _UID_B, _KEY_B)])
                cache = self._cache(f"cached-{layout}.json", (layout, "10001", _KEY_A), (layout, "10002", "stale!KEY@0000#0"), (layout, "10002", _KEY_B))
                before = cache.read_bytes()
                entries = {record["uin"]: record["keys"] for record in self.records("-r", root, "-k", cache)}
                for uin, key in (("10001", _KEY_A), ("10002", _KEY_B)):
                    (entry,) = entries[uin]
                    self.assertEqual(tuple(entry), ENTRY_FIELDS)
                    self.assertEqual((entry["name"], entry["pattern"], entry["key"], entry["hmac_algorithm"], entry["key_note"]), ("nt", "*.db", key, "HMAC_SHA1", {"source": "key cache", "kdf": "sha512"}))
                self.assertEqual(cache.read_bytes(), before, "脚本只读缓存")

    def test_account_without_settings_db_cannot_be_verified(self) -> None:
        for layout in ("windows", "linux"):
            with self.subTest(layout=layout):
                root = self._build(layout, f"unverifiable-{layout}", [("10001", _UID_A, None)])
                cache = self._cache(f"unverifiable-{layout}.json", (layout, "10001", _KEY_A))
                (entry,) = self.records("-r", root, "-k", cache)[0]["keys"]
                self.assertEqual((entry["key"], entry["key_note"]), (None, {"reason": "no settings.db"}))

    def test_data_of_another_system_without_a_usable_cached_key(self) -> None:
        root = self._build(_FOREIGN, "foreign", [("10001", _UID_A, _KEY_A)])
        caches = {
            "没有给出缓存": (None, "no key"),
            "缓存里没有这个账号": (self._cache("foreign-other-uin.json", (_FOREIGN, "10002", _KEY_A)), "no key"),
            "缓存里是另一个平台的密钥": (self._cache("foreign-other-platform.json", (_NATIVE, "10001", _KEY_A)), "no key"),
            "缓存里的密钥不匹配": (self._cache("foreign-mismatch.json", (_FOREIGN, "10001", _KEY_B)), "key mismatch"),
        }
        for situation, (cache, reason) in caches.items():
            with self.subTest(situation=situation):
                result = self.get_keys("-r", root, *(("-k", cache) if cache else ()))
                self.assertEqual(result.code, 0, result.err)
                (entry,) = result.json()[0]["keys"]
                self.assertEqual((entry["key"], entry["key_note"]), (None, {"reason": reason}))
                self.assertIn("10001", result.err, "未取得密钥的账号须在 stderr 说明")

    def test_filter_by_uin_or_uid(self) -> None:
        root = self._build(_FOREIGN, "filter", [("10001", _UID_A, _KEY_A), ("10002", _UID_B, _KEY_B)])
        for qq, expected in (("10002", ["10002"]), (_UID_A, ["10001"]), ("99999", [])):
            with self.subTest(qq=qq):
                self.assertEqual([record["uin"] for record in self.records("-r", root, "-a", qq)], expected)

    def test_windows_accounts_are_listed_even_without_login_db(self) -> None:
        root = self.base / "windows-no-login"
        roots.windows_account(root, "10001", None)
        (record,) = self.records("-P", "windows", "-r", root)
        self.assertEqual((record["uin"], record["uid"]), ("10001", ""))

    def test_linux_accounts_cannot_be_listed_without_login_db(self) -> None:
        root = self.base / "linux-no-login"
        (root / roots.account_dir_name(_UID_A) / "nt_db").mkdir(parents=True)
        result = self.get_keys("-P", "linux", "-r", root)
        self.assertNotEqual(result.code, 0)
        self.assertEqual(result.out, "")
        self.assertIn("login.db", result.err)

    def test_root_holding_no_account_is_an_error(self) -> None:
        root = self.base / "windows-empty"
        root.mkdir()
        result = self.get_keys("-P", "windows", "-r", root)
        self.assertNotEqual(result.code, 0)
        self.assertEqual(result.out, "")

    def test_unusable_cache_file_is_an_error_naming_the_file(self) -> None:
        root = self._build(_FOREIGN, "bad-cache", [("10001", _UID_A, _KEY_A)])
        text_file = self.base / "keys.txt"
        text_file.write_text("# 来源: windows\n10001 first!KEY@0000#1\n", encoding="utf-8")
        for situation, cache in {"不是 JSON": text_file, "文件不存在": self.base / "absent.json"}.items():
            with self.subTest(situation=situation):
                result = self.get_keys("-r", root, "-k", cache)
                self.assertNotEqual(result.code, 0)
                self.assertEqual(result.out, "")
                self.assertIn(cache.name, result.err)

    def test_paths_with_non_ascii_names(self) -> None:
        root = self._build(_FOREIGN, "数据 根目录 😀", [("10001", _UID_A, _KEY_A)])
        cache = self._cache("缓存 😀.json", (_FOREIGN, "10001", _KEY_A))
        (record,) = self.records("-r", root, "-k", cache)
        self.assertEqual(record["keys"][0]["key"], _KEY_A)
        self.assertTrue(Path(record["db_dir"]).is_dir())


class ArgumentTests(_CliCase):
    def test_help(self) -> None:
        for option in ("-h", "--help"):
            with self.subTest(option=option):
                result = self.get_keys(option)
                self.assertEqual((result.code, result.err), (0, ""))
                self.assertIn("--key-cache", result.out)
                self.assertNotIn("\x1b[", result.out, "输出不是终端时不带样式")

    def test_invalid_arguments_exit_with_2(self) -> None:
        for args in (("--no-such-option",), ("-P", "macos"), ("-r",)):
            with self.subTest(args=args):
                result = self.get_keys(*args)
                self.assertEqual((result.code, result.out), (2, ""))


class BuilderCrossCheckTests(_CliCase):
    def test_login_db_built_for_tests_is_what_the_script_reads(self) -> None:
        # 反向检验构造器: 它写出的 login.db 由脚本读出同样的 uin 与 uid
        root = self.base / "cross-check"
        roots.linux_accounts(root, [("10001", _UID_A, "甲", None)], nested=True)
        (record,) = self.records("-P", "linux", "-r", root)
        self.assertEqual((record["uin"], record["uid"]), ("10001", _UID_A))
        self.assertEqual(qqnt.PRE_LOGIN_KEY, b"BD156D6710D54D8782F4")


if __name__ == "__main__":
    unittest.main()
