"""cli.keyscan.login_db: 解密 login.db 并读出登录过的账号。

判定基准: 标准库 sqlite3 写入的行。样本由 support.qqnt 用 QQ 内置的预登录口令加密，-wal 同样逐帧加密。
"""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import qqnt

from cli.keyscan.login_db import Account, read_accounts

__all__ = []

_A = Account(uin="10001", uid="u_fakeUID_aaaaaaaaaaaa", nick="测试昵称 甲")
_B = Account(uin="10002", uid="u_fakeUID_bbbbbbbbbbbb", nick="nick B")
_C = Account(uin="10003", uid="u_fakeUID_cccccccccccc", nick="丙")


def _create(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE TABLE login_table ("1000" TEXT, "1001" TEXT, "1007" TEXT)')


def _insert(*accounts: Account):
    def populate(conn: sqlite3.Connection) -> None:
        conn.executemany("INSERT INTO login_table VALUES (?, ?, ?)", accounts)
    return populate


class _LoginDbCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "login.db"


class MainFileTests(_LoginDbCase):
    def _write(self, populate, *, passphrase: bytes = qqnt.PRE_LOGIN_KEY, page_hmac: str = "sha1") -> None:
        self.path.write_bytes(qqnt.encrypt_database(qqnt.plain_database(populate, page_hmac=page_hmac), passphrase, page_hmac=page_hmac))

    def test_accounts_are_read_with_uin_uid_and_nickname(self) -> None:
        self._write(lambda conn: (_create(conn), _insert(_A, _B)(conn)))
        self.assertEqual(read_accounts(self.path), [_A, _B])

    def test_page_hmac_algorithm_is_detected(self) -> None:
        self._write(lambda conn: (_create(conn), _insert(_A)(conn)), page_hmac="sha512")
        self.assertEqual(read_accounts(self.path), [_A])

    def test_missing_values_become_empty_text(self) -> None:
        self._write(lambda conn: (_create(conn), conn.execute("INSERT INTO login_table VALUES ('10001', NULL, NULL)")))
        self.assertEqual(read_accounts(self.path), [Account(uin="10001", uid="", nick="")])

    def test_database_spanning_several_pages(self) -> None:
        many = [Account(uin=str(20000 + index), uid=f"u_fakeUID_{index:012d}", nick="昵称" * 20) for index in range(120)]
        self._write(lambda conn: (_create(conn), _insert(*many)(conn)))
        self.assertEqual(read_accounts(self.path), many)

    def test_file_encrypted_with_another_passphrase(self) -> None:
        self._write(lambda conn: (_create(conn), _insert(_A)(conn)), passphrase=b"not-the-built-in-key")
        with self.assertRaises(OSError):
            read_accounts(self.path)

    def test_database_without_login_table(self) -> None:
        self._write(lambda conn: conn.execute("CREATE TABLE other (x)"))
        with self.assertRaises(OSError):
            read_accounts(self.path)

    def test_missing_file(self) -> None:
        with self.assertRaises(OSError):
            read_accounts(self.path)

    def test_source_file_is_not_modified(self) -> None:
        self._write(lambda conn: (_create(conn), _insert(_A)(conn)))
        before = self.path.read_bytes()
        read_accounts(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([entry.name for entry in self.path.parent.iterdir()], ["login.db"])


class WalTests(_LoginDbCase):
    """QQ 运行时最近的登录记录还在 -wal 里；只采用其中已提交、且属于当前这一代 WAL 的帧。"""

    def _write(self, populate_wal, *, edit=None) -> None:
        """主文件里只有账号甲；populate_wal 的改动留在 -wal 中，edit 在加密前改写帧序列。"""
        plain, wal = qqnt.plain_database_with_wal(lambda conn: (_create(conn), _insert(_A)(conn)), populate_wal)
        self.path.write_bytes(qqnt.encrypt_database(plain, qqnt.PRE_LOGIN_KEY))
        self.path.with_name("login.db-wal").write_bytes(qqnt.encrypt_wal(wal, qqnt.PRE_LOGIN_KEY, edit=edit))

    @staticmethod
    def _two_transactions(conn: sqlite3.Connection) -> None:
        _insert(_B)(conn)
        conn.commit()
        _insert(_C)(conn)

    def test_rows_committed_only_in_the_wal_are_visible(self) -> None:
        self._write(_insert(_B))
        self.assertEqual(read_accounts(self.path), [_A, _B])

    def test_later_transactions_override_earlier_ones(self) -> None:
        self._write(self._two_transactions)
        self.assertEqual(read_accounts(self.path), [_A, _B, _C])

    def test_trailing_frames_without_a_commit_are_ignored(self) -> None:
        self._write(self._two_transactions, edit=lambda frames: [*frames[:-1], frames[-1]._replace(commit=0)])
        self.assertEqual(read_accounts(self.path), [_A, _B])

    def test_frames_left_over_from_an_older_wal_generation_are_ignored(self) -> None:
        # checkpoint 重置 WAL 后旧帧仍留在文件里，帧头的 salt 与文件头不同
        self._write(self._two_transactions, edit=lambda frames: [*frames[:-1], frames[-1]._replace(salt=bytes(8))])
        self.assertEqual(read_accounts(self.path), [_A, _B])

    def test_wal_that_is_not_a_wal_file_is_ignored(self) -> None:
        self._write(_insert(_B))
        self.path.with_name("login.db-wal").write_bytes(b"not a wal file" * 400)
        self.assertEqual(read_accounts(self.path), [_A])

    def test_wal_with_a_corrupted_frame_stops_at_that_frame(self) -> None:
        self._write(self._two_transactions)
        wal_path = self.path.with_name("login.db-wal")
        wal = bytearray(wal_path.read_bytes())
        wal[-100] ^= 0x01
        wal_path.write_bytes(bytes(wal))
        self.assertEqual(read_accounts(self.path), [_A, _B])


if __name__ == "__main__":
    unittest.main()
