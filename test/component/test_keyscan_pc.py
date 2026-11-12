"""cli.keyscan.pc: 为 windows 与 linux 布局的账号取得密钥，先试缓存，再扫描进程内存。

判定基准: 手工设定的账号、密钥与假内存，各账号的 settings.db 由 support.qqnt 加密。
替身: 进程后端 (read_keys_pc 的 backend 参数)，接口同 process_windows / process_linux，后者由 test_keyscan_process 对真实系统检验。
"""

import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from support.memory import FakeBackend, memory_with_key
from support.records import ENTRY_FIELDS, RECORD_FIELDS
from support.roots import windows_account

from cli.keyscan.locate import PcAccount
from cli.keyscan.pc import read_keys_pc

__all__ = []

_KEY = b"pLACEhold3r!@#$%"
_OTHER = b"other!KEY@00000#"


class _PcCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # read_keys_pc 默认向 stderr 报告各账号的结果，这里不关心
        quiet = redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def _account(self, uin: str, key: bytes | None, *, uid: str = "", page_hmac: str = "sha1") -> PcAccount:
        db_dir = windows_account(self.root, uin, key, page_hmac=page_hmac)
        return PcAccount(uin=uin, uid=uid, qq_path=str(db_dir.parent), db_dir=str(db_dir))

    def _read(self, accounts: list[PcAccount], *, backend, cached: dict[str, list[bytes]] | None = None, qq: str | None = None, layout: str = "windows") -> list[dict[str, object]]:
        return read_keys_pc(qq, accounts, layout=layout, cached=cached or {}, backend=backend, verbose=False)

    def _entry(self, account: PcAccount, **options) -> dict[str, object]:
        return self._read([account], **options)[0]["keys"][0]


class RecordTests(_PcCase):
    def test_record_carries_account_fields_and_one_rule_for_all_databases(self) -> None:
        account = self._account("10001", _KEY, uid="u_fakeUID_aaaaaaaaaaaa")
        (record,) = self._read([account], backend=FakeBackend({7: memory_with_key(_KEY)}), layout="linux")
        self.assertEqual(tuple(record), RECORD_FIELDS)
        self.assertEqual({name: record[name] for name in RECORD_FIELDS[:-1]}, {"platform": "linux", "qq_path": account.qq_path, "user": "linux", "uin": "10001", "uid": "u_fakeUID_aaaaaaaaaaaa", "uid_hash": "", "path_hash": "", "db_dir": account.db_dir})
        (entry,) = record["keys"]
        self.assertEqual(tuple(entry), ENTRY_FIELDS)
        self.assertEqual((entry["name"], entry["pattern"], entry["key"], entry["hmac_algorithm"]), ("nt", "*.db", _KEY.decode(), "HMAC_SHA1"))
        self.assertEqual(entry["key_note"], {"pid": "7", "kdf": "sha512"})
        self.assertEqual(sorted((file["name"], file["size"]) for file in entry["files"]), [("nt_msg.db", 10), ("settings.db", 5120)])

    def test_hmac_algorithm_follows_the_database(self) -> None:
        entry = self._entry(self._account("10001", _KEY, page_hmac="sha512"), backend=FakeBackend({7: memory_with_key(_KEY)}))
        self.assertEqual((entry["key"], entry["hmac_algorithm"]), (_KEY.decode(), "HMAC_SHA512"))


class ScanTests(_PcCase):
    def test_each_account_is_matched_to_the_process_holding_its_key(self) -> None:
        accounts = [self._account("10001", _KEY), self._account("10002", _OTHER)]
        records = self._read(accounts, backend=FakeBackend({7: memory_with_key(_OTHER), 8: memory_with_key(_KEY)}))
        self.assertEqual([(record["uin"], record["keys"][0]["key"], record["keys"][0]["key_note"]["pid"]) for record in records], [("10001", _KEY.decode(), "8"), ("10002", _OTHER.decode(), "7")])

    def test_scanning_stops_once_every_account_has_its_key(self) -> None:
        backend = FakeBackend({7: memory_with_key(_KEY), 8: memory_with_key(_OTHER)})
        self._read([self._account("10001", _KEY)], backend=backend)
        self.assertEqual(backend.scanned, [7])

    def test_process_that_cannot_be_read_does_not_hide_a_key_found_elsewhere(self) -> None:
        entry = self._entry(self._account("10001", _KEY), backend=FakeBackend({7: memory_with_key(_KEY)}, denied=(9,), unreadable=(10,)))
        self.assertEqual(entry["key"], _KEY.decode())


class UnresolvedTests(_PcCase):
    """未取得密钥的账号仍然列出，key 为 None，key_note.reason 说明原因。"""

    def _reason(self, account: PcAccount, **options) -> str:
        entry = self._entry(account, **options)
        self.assertIsNone(entry["key"])
        return entry["key_note"]["reason"]

    def test_no_settings_db_to_verify_against(self) -> None:
        backend = FakeBackend({7: memory_with_key(_KEY)})
        self.assertEqual(self._reason(self._account("10001", None), backend=backend), "no settings.db")
        self.assertEqual(backend.scanned, [])

    def test_key_is_in_no_process(self) -> None:
        self.assertEqual(self._reason(self._account("10001", _KEY), backend=FakeBackend({7: memory_with_key(_OTHER)})), "not found")
        self.assertEqual(self._reason(self._account("10002", _KEY), backend=FakeBackend({})), "not found")

    def test_a_process_refused_to_open(self) -> None:
        self.assertEqual(self._reason(self._account("10001", _KEY), backend=FakeBackend({7: memory_with_key(_OTHER)}, denied=(9,))), "permission denied")

    def test_a_process_opened_but_gave_no_bytes(self) -> None:
        self.assertEqual(self._reason(self._account("10001", _KEY), backend=FakeBackend({}, unreadable=(9,))), "permission denied")

    def test_data_of_another_system_cannot_be_scanned(self) -> None:
        self.assertEqual(self._reason(self._account("10001", _KEY), backend=None), "no key")

    def test_cached_keys_do_not_fit_and_scanning_is_impossible(self) -> None:
        self.assertEqual(self._reason(self._account("10001", _KEY), backend=None, cached={"10001": [_OTHER]}), "key mismatch")


class CacheTests(_PcCase):
    def test_cached_key_is_verified_and_used_without_scanning(self) -> None:
        account = self._account("10001", _KEY)
        for backend in (None, FakeBackend({7: memory_with_key(_KEY)})):
            with self.subTest(backend=backend):
                entry = self._entry(account, backend=backend, cached={"10001": [_OTHER, _KEY], "10002": [_KEY]})
                self.assertEqual((entry["key"], entry["key_note"]), (_KEY.decode(), {"source": "key cache", "kdf": "sha512"}))
                if backend is not None:
                    self.assertEqual(backend.scanned, [])

    def test_key_cached_for_another_uin_is_not_tried(self) -> None:
        entry = self._entry(self._account("10001", _KEY), backend=None, cached={"10002": [_KEY]})
        self.assertEqual((entry["key"], entry["key_note"]), (None, {"reason": "no key"}))

    def test_stale_cached_key_falls_back_to_scanning(self) -> None:
        entry = self._entry(self._account("10001", _KEY), backend=FakeBackend({7: memory_with_key(_KEY)}), cached={"10001": [_OTHER]})
        self.assertEqual((entry["key"], entry["key_note"]), (_KEY.decode(), {"pid": "7", "kdf": "sha512"}))

    def test_only_accounts_missing_from_the_cache_are_scanned_for(self) -> None:
        accounts = [self._account("10001", _KEY), self._account("10002", _OTHER)]
        records = self._read(accounts, backend=FakeBackend({7: memory_with_key(_OTHER)}), cached={"10001": [_KEY]})
        self.assertEqual([record["keys"][0]["key_note"] for record in records], [{"source": "key cache", "kdf": "sha512"}, {"pid": "7", "kdf": "sha512"}])


class FilterTests(_PcCase):
    def test_filter_matches_uin_or_uid(self) -> None:
        accounts = [self._account("10001", _KEY, uid="u_fakeUID_aaaaaaaaaaaa"), self._account("10002", _OTHER, uid="u_fakeUID_bbbbbbbbbbbb")]
        for qq, expected in (("10002", ["10002"]), ("u_fakeUID_aaaaaaaaaaaa", ["10001"]), (None, ["10001", "10002"])):
            with self.subTest(qq=qq):
                self.assertEqual([record["uin"] for record in self._read(accounts, backend=None, qq=qq)], expected)

    def test_no_matching_account_means_no_scan(self) -> None:
        backend = FakeBackend({7: memory_with_key(_KEY)})
        self.assertEqual(self._read([self._account("10001", _KEY)], backend=backend, qq="99999"), [])
        self.assertEqual(backend.scanned, [])


if __name__ == "__main__":
    unittest.main()
