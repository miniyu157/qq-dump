"""app.key_cache: 把新取得的密钥记入缓存文件。

判定基准: 手写的记录；写出的文件再交给 cli 一侧的 read_cached_keys 读回，守住读写两端对格式的一致理解。
密钥均为假占位值。
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import REPO
from support.records import key_entry, record

from app.key_cache import DEFAULT_KEY_CACHE, remember_keys
from cli.keyscan.key_cache import read_cached_keys

__all__ = []


def _found(platform: str, uin: str, key: str, **fields: str) -> dict[str, object]:
    return record(platform, uin, key_entry(key, files=(("nt_msg.db", 10),)), **fields)


class RememberKeysTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # 目录尚不存在，由 remember_keys 创建
        self.cache = Path(temporary.name) / "cache" / "keys.json"

    def _stored(self) -> list[dict[str, object]]:
        return json.loads(self.cache.read_text(encoding="utf-8"))

    def test_new_keys_are_stored_without_run_specific_fields(self) -> None:
        records = [_found("windows", "10001", "pLACEhold3r!@#$%"), record("windows", "10002", key_entry(None, reason="not found"))]
        added = remember_keys(self.cache, records)
        self.assertEqual([entry["uin"] for entry in added], ["10001"])
        self.assertEqual(self._stored(), added)
        self.assertEqual(added[0]["keys"], [{"name": "nt", "pattern": "*.db", "key": "pLACEhold3r!@#$%", "hmac_algorithm": "HMAC_SHA1"}])
        self.assertEqual({name: value for name, value in added[0].items() if name != "keys"}, {name: value for name, value in records[0].items() if name != "keys"})

    def test_given_records_are_left_untouched(self) -> None:
        records = [_found("windows", "10001", "pLACEhold3r!@#$%")]
        snapshot = json.dumps(records)
        remember_keys(self.cache, records)
        self.assertEqual(json.dumps(records), snapshot)

    def test_stored_keys_are_read_back_by_the_cli_side(self) -> None:
        remember_keys(self.cache, [_found("windows", "10001", "pLACEhold3r!@#$%"), _found("linux", "10001", "#starts\"with'hash\\")])
        remember_keys(self.cache, [_found("windows", "10001", "second!KEY@000#2")])
        self.assertEqual(read_cached_keys(self.cache, platform="windows"), {"10001": [b"second!KEY@000#2", b"pLACEhold3r!@#$%"]})
        self.assertEqual(read_cached_keys(self.cache, platform="linux"), {"10001": [b"#starts\"with'hash\\"]})

    def test_known_key_is_not_stored_again(self) -> None:
        remember_keys(self.cache, [_found("windows", "10001", "pLACEhold3r!@#$%")])
        before = self.cache.read_bytes()
        # 同一密钥经缓存取回后，数据位置可能已经不同，仍视为已记入
        again = _found("windows", "10001", "pLACEhold3r!@#$%", db_dir="拷贝/nt_db")
        self.assertEqual(remember_keys(self.cache, [again, again]), [])
        self.assertEqual(self.cache.read_bytes(), before)

    def test_same_uin_with_another_platform_or_key_is_stored_separately(self) -> None:
        remember_keys(self.cache, [_found("windows", "10001", "pLACEhold3r!@#$%")])
        added = remember_keys(self.cache, [_found("linux", "10001", "pLACEhold3r!@#$%"), _found("windows", "10001", "second!KEY@000#2")])
        self.assertEqual(len(added), 2)
        self.assertEqual([(entry["platform"], entry["keys"][0]["key"]) for entry in self._stored()], [("windows", "pLACEhold3r!@#$%"), ("linux", "pLACEhold3r!@#$%"), ("windows", "second!KEY@000#2")])

    def test_existing_content_is_kept_as_it_is(self) -> None:
        # 用户把 key 的完整输出直接存成缓存: 含 files、key_note 与未取得的密钥，编码为 UTF-16
        existing = [_found("windows", "10001", "pLACEhold3r!@#$%"), record("windows", "10002", key_entry(None, reason="not found"))]
        self.cache.parent.mkdir()
        self.cache.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-16")
        added = remember_keys(self.cache, [_found("windows", "10001", "pLACEhold3r!@#$%"), _found("windows", "10002", "second!KEY@000#2")])
        self.assertEqual([entry["uin"] for entry in added], ["10002"])
        self.assertEqual(self._stored(), [*existing, *added])

    def test_nothing_to_store_creates_nothing(self) -> None:
        self.assertEqual(remember_keys(self.cache, [record("windows", "10001", key_entry(None, reason="not found"))]), [])
        self.assertEqual(remember_keys(self.cache, []), [])
        self.assertFalse(self.cache.parent.exists())

    def test_invalid_existing_content_is_reported_and_not_overwritten(self) -> None:
        self.cache.parent.mkdir()
        for content in ("# 来源: windows\n10001 pLACEhold3r!@#$%\n", '{"records": []}', '["text"]'):
            with self.subTest(content=content):
                self.cache.write_text(content, encoding="utf-8")
                with self.assertRaises(OSError):
                    remember_keys(self.cache, [_found("windows", "10001", "pLACEhold3r!@#$%")])
                self.assertEqual(self.cache.read_text(encoding="utf-8"), content)
        # 失败时也不留下临时文件
        self.assertEqual([path.name for path in self.cache.parent.iterdir()], ["keys.json"])


class DefaultLocationTests(unittest.TestCase):
    def test_default_cache_is_inside_the_ignored_cache_directory(self) -> None:
        self.assertEqual(DEFAULT_KEY_CACHE, REPO / ".cache" / "keys.json")
        self.assertIn(".cache/", (REPO / ".gitignore").read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
