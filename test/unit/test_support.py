"""support 构造器的自检: 它们充当其余测试的判定基准，自身须先被独立的基准检验。

判定基准: FIPS-197 附录 C.3 与 SP 800-38A F.2.5 的 AES-256 标准向量；protobuf 编码文档中的字节示例。
"""

import unittest

from support import qqnt
from support.aes import aes256_cbc_encrypt
from support.wire import field, fixed32, fixed64, varint

__all__ = []


class AesEncryptTests(unittest.TestCase):
    def test_fips197_single_block(self) -> None:
        cipher = aes256_cbc_encrypt(bytes(range(32)), bytes(16), bytes.fromhex("00112233445566778899aabbccddeeff"))
        self.assertEqual(cipher.hex(), "8ea2b7ca516745bfeafc49904b496089")

    def test_sp800_38a_cbc_chain(self) -> None:
        key = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
        plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e5130c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710")
        cipher = aes256_cbc_encrypt(key, bytes(range(16)), plain)
        self.assertEqual(cipher.hex(), "f58c4c04d6e5f1ba779eabfb5f7bfbd69cfc4e967edb808d679f777bc6702c7d39f23369a9d9bacfa530e26304231461b2eb05e2c39be9fcda6c19078c6a9d1b")

    def test_rejects_wrong_sizes(self) -> None:
        for key, iv, plain in ((bytes(16), bytes(16), bytes(16)), (bytes(32), bytes(8), bytes(16)), (bytes(32), bytes(16), bytes(15))):
            with self.subTest(key=len(key), iv=len(iv), plain=len(plain)), self.assertRaises(ValueError):
                aes256_cbc_encrypt(key, iv, plain)


class WireEncoderTests(unittest.TestCase):
    def test_documented_examples(self) -> None:
        self.assertEqual(varint(1), b"\x01")
        self.assertEqual(varint(150), bytes.fromhex("9601"))
        self.assertEqual(varint(300), bytes.fromhex("ac02"))
        self.assertEqual(field(1, 150), bytes.fromhex("089601"))
        self.assertEqual(field(2, b"testing"), bytes.fromhex("120774657374696e67"))
        self.assertEqual(field(3, field(1, 150)), bytes.fromhex("1a03089601"))

    def test_fixed_width_tags(self) -> None:
        self.assertEqual(fixed64(1, bytes(8)), b"\x09" + bytes(8))
        self.assertEqual(fixed32(1, bytes(4)), b"\x0d" + bytes(4))


class DatabaseLayoutTests(unittest.TestCase):
    def test_reserve_holds_iv_and_digest_in_whole_blocks(self) -> None:
        self.assertEqual([qqnt.reserve_size(name) for name in ("sha1", "sha256", "sha512")], [48, 48, 80])

    def test_encrypted_file_is_header_plus_whole_pages_starting_with_salt(self) -> None:
        header = b"QQ_NT DB".ljust(qqnt.HEADER_SIZE, b"\x00")
        salt = bytes(range(16))
        plain = qqnt.plain_database(lambda conn: conn.execute("CREATE TABLE t (x)"))
        encrypted = qqnt.encrypt_database(plain, b"passphrase", header=header, salt=salt)
        self.assertEqual(len(encrypted), qqnt.HEADER_SIZE + len(plain))
        self.assertEqual(encrypted[:qqnt.HEADER_SIZE], header)
        self.assertEqual(encrypted[qqnt.HEADER_SIZE:qqnt.HEADER_SIZE + 16], salt)
        self.assertNotIn(b"SQLite format 3", encrypted)
        self.assertNotIn(b"CREATE TABLE", encrypted)


if __name__ == "__main__":
    unittest.main()
