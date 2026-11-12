"""cli.keyscan.key_cache: 从密钥缓存文件读出某个平台各账号的候选密钥。

判定基准: 手写的缓存文件内容。密钥均为假占位值。
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.records import key_entry, record

from cli.keyscan.key_cache import read_cached_keys

__all__ = []


def _minimal(platform: str, uin: str, *keys: str | None) -> dict[str, object]:
    """只含读取所需字段的记录。"""
    return {"platform": platform, "uin": uin, "keys": [{"key": key} for key in keys]}


class ReadCachedKeysTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "keys.json"

    def _read(self, records: object, platform: str = "windows", encoding: str = "utf-8") -> dict[str, list[bytes]]:
        self.path.write_text(json.dumps(records, ensure_ascii=False), encoding=encoding)
        return read_cached_keys(self.path, platform=platform)

    def test_keys_are_grouped_by_uin_within_the_platform(self) -> None:
        records = [_minimal("windows", "10001", "pLACEhold3r!@#$%"), _minimal("linux", "10001", "linux!KEY@00000#"), _minimal("windows", "10002", "#starts\"with'hash\\")]
        self.assertEqual(self._read(records), {"10001": [b"pLACEhold3r!@#$%"], "10002": [b"#starts\"with'hash\\"]})
        self.assertEqual(self._read(records, platform="linux"), {"10001": [b"linux!KEY@00000#"]})
        self.assertEqual(self._read(records, platform="android"), {})

    def test_later_records_come_first(self) -> None:
        records = [_minimal("windows", "10001", "first!KEY@0000#1"), _minimal("windows", "10001", "second!KEY@000#2")]
        self.assertEqual(self._read(records), {"10001": [b"second!KEY@000#2", b"first!KEY@0000#1"]})

    def test_entries_without_a_key_are_skipped(self) -> None:
        self.assertEqual(self._read([_minimal("windows", "10001", None), _minimal("windows", "10002")]), {})
        self.assertEqual(self._read([]), {})

    def test_full_get_keys_output_can_serve_as_a_cache(self) -> None:
        full = record("windows", "10001", key_entry("pLACEhold3r!@#$%", files=(("nt_msg.db", 10),)), uid="u_a", db_dir="数据/10001/nt_qq/nt_db")
        unresolved = record("windows", "10002", key_entry(None, reason="not found"))
        self.assertEqual(self._read([full, unresolved]), {"10001": [b"pLACEhold3r!@#$%"]})

    def test_files_written_by_powershell_redirection_are_readable(self) -> None:
        # Windows PowerShell 的 > 写出带 BOM 的 UTF-16，较新的版本写 UTF-8
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                self.assertEqual(self._read([_minimal("windows", "10001", "pLACEhold3r!@#$%")], encoding=encoding), {"10001": [b"pLACEhold3r!@#$%"]})


class InvalidCacheTests(unittest.TestCase):
    """读不了或结构不符的缓存以 OSError 报出，消息带上文件路径；不把它当作空缓存。"""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "keys.json"

    def _assert_rejected(self, content: str) -> str:
        self.path.write_text(content, encoding="utf-8")
        with self.assertRaises(OSError) as raised:
            read_cached_keys(self.path, platform="windows")
        self.assertIn(str(self.path), str(raised.exception))
        return str(raised.exception)

    def test_missing_file(self) -> None:
        with self.assertRaises(OSError):
            read_cached_keys(self.path, platform="windows")

    def test_text_that_is_not_json(self) -> None:
        self._assert_rejected("# 来源: windows\n10001 pLACEhold3r!@#$%\n")

    def test_top_level_is_not_an_array(self) -> None:
        self._assert_rejected(json.dumps({"records": [_minimal("windows", "10001", "pLACEhold3r!@#$%")]}))

    def test_malformed_records(self) -> None:
        malformed = {
            "记录不是对象": "text",
            "缺少 platform": {"uin": "10001", "keys": []},
            "uin 不是文本": {"platform": "windows", "uin": 10001, "keys": []},
            "缺少 keys": {"platform": "windows", "uin": "10001"},
            "条目缺少 key": {"platform": "windows", "uin": "10001", "keys": [{"name": "nt"}]},
            "key 不是文本": {"platform": "windows", "uin": "10001", "keys": [{"key": 1}]},
        }
        for reason, broken in malformed.items():
            with self.subTest(reason=reason):
                self._assert_rejected(json.dumps([_minimal("windows", "10001", "pLACEhold3r!@#$%"), broken]))

    def test_message_names_the_offending_record_even_on_another_platform(self) -> None:
        message = self._assert_rejected(json.dumps([_minimal("windows", "10001", "pLACEhold3r!@#$%"), {"platform": "linux"}]))
        self.assertIn("第 2 条", message)


if __name__ == "__main__":
    unittest.main()
