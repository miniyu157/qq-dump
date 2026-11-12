"""cli/decrypt_db.py 的命令行: 把 QQ NT 数据库解密为标准布局的明文 SQLite 库。

判定基准: 标准库 sqlite3 写入的行 = 导出库经标准库 sqlite3 读出的行。样本由 support.qqnt 加密，
解密由真实的 sqlcipher 完成，因此这里同时反向检验了构造器。
超过 1 GiB 的库的锁页迁移无法用合成数据构造，不在这里验证，见实机层。
"""

import hashlib
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import qqnt, roots
from support.cli import Result, child_env, run_script
from support.requires import known_issue, needs_sqlcipher, sqlcipher_opens_non_ascii_paths

__all__ = []

_NT_KEY = "0123456789abcdef0123456789abcdef"
_GPRO_KEY = "fedcba9876543210fedcba9876543210"
# PC 的 raw_key 可含 =、: 与引号
_RAW_KEY = "p=a:s'w0rd!KEY#1"
_ROWS = [(index, f"消息 {index} " + "内容" * 30) for index in range(150)]
_WAL_ROWS = [(1000, "只在 WAL 中")]


def _populate(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, text TEXT)")
    conn.executemany("INSERT INTO messages VALUES (?, ?)", _ROWS)


def _rows(path: Path) -> list[tuple[int, str]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT id, text FROM messages ORDER BY id").fetchall()
    finally:
        conn.close()


def _snapshot(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.rglob("*")) if path.is_file()}


class _DecryptCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.base = Path(temporary.name).resolve()
        cls.source = cls.base / "source"
        cls.source.mkdir()

        sha1 = qqnt.plain_database(_populate, page_hmac="sha1")
        sha512 = qqnt.plain_database(_populate, page_hmac="sha512")
        (cls.source / "nt_msg.db").write_bytes(qqnt.encrypt_database(sha1, _NT_KEY.encode(), header=roots.nt_header(roots.RAND)))
        (cls.source / "gpro_v1-6_u_x.db").write_bytes(qqnt.encrypt_database(sha512, _GPRO_KEY.encode(), page_hmac="sha512", header=roots.gpro_header(roots.GPRO_SALT)))
        (cls.source / "raw.db").write_bytes(qqnt.encrypt_database(sha1, _RAW_KEY.encode()))
        (cls.source / "wrong_key.db").write_bytes(qqnt.encrypt_database(sha1, b"some other key"))
        # 明文库: 带 QQ 文件头的与不带的
        ordinary = qqnt.plain_database(_populate)
        (cls.source / "plain.db").write_bytes(roots.nt_header(roots.RAND) + ordinary)
        (cls.source / "bare.db").write_bytes(ordinary)
        (cls.source / "empty.db").touch()
        (cls.source / "header_only.db").write_bytes(roots.nt_header(roots.RAND))
        (cls.source / "readme.txt").write_text("不是数据库", encoding="utf-8")
        # 主文件里是 _ROWS，另有一行只提交在 -wal 中
        main, wal = qqnt.plain_database_with_wal(_populate, lambda conn: conn.executemany("INSERT INTO messages VALUES (?, ?)", _WAL_ROWS))
        (cls.source / "wal.db").write_bytes(qqnt.encrypt_database(main, _NT_KEY.encode()))
        (cls.source / "wal.db-wal").write_bytes(qqnt.encrypt_wal(wal, _NT_KEY.encode()))
        cls.source_snapshot = _snapshot(cls.source)

    def setUp(self) -> None:
        temporary = TemporaryDirectory(dir=self.base)
        self.addCleanup(temporary.cleanup)
        self.out = Path(temporary.name) / "out"

    def decrypt(self, *args: str | Path, source: Path | None = None, env: dict[str, str] | None = None) -> Result:
        return run_script("decrypt_db.py", "-d", str(source or self.source), "-o", str(self.out), *map(str, args), env=env)

    def outputs(self) -> list[str]:
        """输出目录下的全部文件，含隐藏的临时文件；目录不存在时为空。"""
        return sorted(str(path.relative_to(self.out)).replace("\\", "/") for path in self.out.rglob("*") if path.is_file()) if self.out.exists() else []


@needs_sqlcipher
class DecryptTests(_DecryptCase):
    def test_database_is_exported_as_plain_sqlite_with_the_same_rows(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "nt_msg.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(self.outputs(), ["nt_msg.db"])
        self.assertTrue((self.out / "nt_msg.db").read_bytes().startswith(b"SQLite format 3\x00"))
        self.assertEqual(_rows(self.out / "nt_msg.db"), _ROWS)

    def test_sha512_database_with_the_algorithm_named(self) -> None:
        self.assertEqual(self.decrypt("-k", f"{_GPRO_KEY}:HMAC_SHA512", "gpro_v1-6_u_x.db").code, 0)
        self.assertEqual(_rows(self.out / "gpro_v1-6_u_x.db"), _ROWS)

    def test_wrong_algorithm_in_the_rule_falls_back_to_the_other_one(self) -> None:
        for rule, name in ((_GPRO_KEY, "gpro_v1-6_u_x.db"), (f"{_GPRO_KEY}:HMAC_SHA1", "gpro_v1-6_u_x.db"), (f"{_NT_KEY}:HMAC_SHA512", "nt_msg.db")):
            with self.subTest(rule=rule, name=name):
                self.assertEqual(self.decrypt("-k", rule, name).code, 0)
                self.assertEqual(_rows(self.out / name), _ROWS)

    def test_key_containing_equals_colon_and_quote(self) -> None:
        for rule in (f"*={_RAW_KEY}", f"*={_RAW_KEY}:HMAC_SHA1", f"raw.db={_RAW_KEY}"):
            with self.subTest(rule=rule):
                self.assertEqual(self.decrypt("-k", rule, "raw.db").code, 0)
                self.assertEqual(_rows(self.out / "raw.db"), _ROWS)

    def test_each_file_uses_the_first_rule_matching_its_name(self) -> None:
        result = self.decrypt("-k", f"gpro_v1-6_*.db={_GPRO_KEY}:HMAC_SHA512", "-k", _NT_KEY, "gpro_v1-6_u_x.db", "nt_msg.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual((_rows(self.out / "gpro_v1-6_u_x.db"), _rows(self.out / "nt_msg.db")), (_ROWS, _ROWS))

    def test_general_rule_placed_first_shadows_the_specific_one(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "-k", f"gpro_v1-6_*.db={_GPRO_KEY}:HMAC_SHA512", "gpro_v1-6_u_x.db", "nt_msg.db")
        self.assertEqual(result.code, 1)
        self.assertEqual(self.outputs(), ["nt_msg.db"])

    def test_all_databases_of_the_directory_are_taken_by_default(self) -> None:
        source = self.base / "only-good"
        source.mkdir(exist_ok=True)
        for name in ("nt_msg.db", "wal.db", "readme.txt"):
            (source / name).write_bytes((self.source / name).read_bytes())
        self.assertEqual(self.decrypt("-k", _NT_KEY, source=source).code, 0)
        self.assertEqual(self.outputs(), ["nt_msg.db", "wal.db"])

    def test_commits_still_in_the_wal_are_included(self) -> None:
        self.assertEqual(self.decrypt("-k", _NT_KEY, "wal.db").code, 0)
        self.assertEqual(_rows(self.out / "wal.db"), [*_ROWS, *_WAL_ROWS])
        self.assertEqual(self.outputs(), ["wal.db"], "导出的是合并后的单个文件")

    def test_source_directory_is_left_untouched(self) -> None:
        self.decrypt("-k", f"gpro_v1-6_*.db={_GPRO_KEY}:HMAC_SHA512", "-k", f"raw.db={_RAW_KEY}", "-k", _NT_KEY, "--copy-plain")
        self.assertEqual(_snapshot(self.source), self.source_snapshot)

    def test_output_name_template_may_add_directories(self) -> None:
        self.assertEqual(self.decrypt("-k", _NT_KEY, "-f", "account 'a'/{filename}/data.db", "nt_msg.db").code, 0)
        self.assertEqual(_rows(self.out / "account 'a'" / "nt_msg.db" / "data.db"), _ROWS)

    # 已知缺陷: 临时文件路径作为命令行参数交给 sqlcipher，Windows 上部分 sqlcipher 构建把参数按 ANSI 代码页接收
    # 却当作 UTF-8 解释，输出路径含非 ASCII 字符时打不开文件。用户名含中文时 %TEMP% 下的自动解密同样受影响
    @known_issue(not sqlcipher_opens_non_ascii_paths())
    def test_output_path_with_non_ascii_characters(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "-f", "账号甲/{filename}", "nt_msg.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(_rows(self.out / "账号甲" / "nt_msg.db"), _ROWS)


@needs_sqlcipher
class FailureTests(_DecryptCase):
    """失败的文件以退出码 1 报告，不留下输出或临时文件，也不影响其余文件。"""

    def test_wrong_key(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "wrong_key.db")
        self.assertEqual(result.code, 1)
        self.assertIn("解密校验失败", result.err)
        self.assertEqual(self.outputs(), [])

    def test_other_files_are_still_exported(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "wrong_key.db", "nt_msg.db")
        self.assertEqual(result.code, 1)
        self.assertEqual(self.outputs(), ["nt_msg.db"])

    def test_failure_keeps_an_output_that_already_exists(self) -> None:
        self.out.mkdir()
        (self.out / "wrong_key.db").write_bytes(b"earlier export")
        self.assertEqual(self.decrypt("-k", _NT_KEY, "wrong_key.db").code, 1)
        self.assertEqual((self.out / "wrong_key.db").read_bytes(), b"earlier export")
        self.assertEqual(self.outputs(), ["wrong_key.db"])

    def test_success_replaces_an_output_that_already_exists(self) -> None:
        self.out.mkdir()
        (self.out / "nt_msg.db").write_bytes(b"earlier export")
        self.assertEqual(self.decrypt("-k", _NT_KEY, "nt_msg.db").code, 0)
        self.assertEqual(_rows(self.out / "nt_msg.db"), _ROWS)

    def test_no_rule_or_an_empty_key_for_the_file(self) -> None:
        for situation, rules in {"没有规则": (), "规则不匹配文件名": ("-k", f"other*.db={_NT_KEY}"), "匹配的规则密钥为空": ("-k", "nt_msg.db=", "-k", _NT_KEY)}.items():
            with self.subTest(situation=situation):
                result = self.decrypt(*rules, "nt_msg.db")
                self.assertEqual(result.code, 1)
                self.assertIn("缺少可用密钥", result.err)
                self.assertEqual(self.outputs(), [])

    def test_file_that_does_not_exist(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "absent.db")
        self.assertEqual(result.code, 1)
        self.assertIn("absent.db", result.err)

    def test_output_name_leaving_the_output_directory_is_refused(self) -> None:
        for template in ("../{filename}", "sub/../../escaped.db", "."):
            with self.subTest(template=template):
                result = self.decrypt("-k", _NT_KEY, "-f", template, "nt_msg.db")
                self.assertEqual(result.code, 1)
                self.assertEqual(self.outputs(), [])
                self.assertFalse((self.out.parent / "nt_msg.db").exists())
                self.assertFalse((self.out.parent / "escaped.db").exists())


@needs_sqlcipher
class PlainDatabaseTests(_DecryptCase):
    """未加密的库不需要密钥；带 1024 字节 QQ 文件头的也算明文库。"""

    def test_plain_databases_are_skipped_by_default_without_failing(self) -> None:
        result = self.decrypt("plain.db", "bare.db")
        self.assertEqual(result.code, 0)
        self.assertEqual(self.outputs(), [])
        self.assertIn("plain.db", result.err)
        self.assertIn("--copy-plain", result.err)

    def test_copy_plain_exports_them_without_the_qq_header(self) -> None:
        result = self.decrypt("--copy-plain", "plain.db", "bare.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(self.outputs(), ["bare.db", "plain.db"])
        for name in ("plain.db", "bare.db"):
            with self.subTest(name=name):
                self.assertTrue((self.out / name).read_bytes().startswith(b"SQLite format 3\x00"))
                self.assertEqual(_rows(self.out / name), _ROWS)

    def test_skip_empty_passes_over_files_too_small_to_hold_a_page(self) -> None:
        result = self.decrypt("-k", _NT_KEY, "--skip-empty", "empty.db", "header_only.db", "nt_msg.db")
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual(self.outputs(), ["nt_msg.db"])


class ArgumentTests(_DecryptCase):
    """不需要 sqlcipher 就能判定的部分。"""

    def test_help(self) -> None:
        result = run_script("decrypt_db.py", "-h")
        self.assertEqual((result.code, result.err), (0, ""))
        self.assertIn("--copy-plain", result.out)
        self.assertNotIn("\x1b[", result.out)

    def test_invalid_arguments_exit_with_2(self) -> None:
        for args in ((), ("-d", str(self.source), "-k", f"{_NT_KEY}:HMAC_MD5"), ("-d", str(self.source), "--no-such-option")):
            with self.subTest(args=args):
                result = run_script("decrypt_db.py", *args)
                self.assertEqual((result.code, result.out), (2, ""))

    def test_missing_sqlcipher_is_reported_before_any_work(self) -> None:
        empty = self.base / "empty-path"
        empty.mkdir(exist_ok=True)
        result = self.decrypt("-k", _NT_KEY, "nt_msg.db", env=child_env(PATH=str(empty)))
        self.assertEqual(result.code, 1)
        self.assertIn("sqlcipher", result.err)
        self.assertEqual(self.outputs(), [])


if __name__ == "__main__":
    unittest.main()
