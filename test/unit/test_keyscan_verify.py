"""cli.keyscan.verify: 判断一个口令能否解开某个 QQ NT 数据库，并探测页 HMAC 与 KDF 的算法。

判定基准: support.qqnt 按 SQLCipher 页格式构造的加密库 (该构造器在契约层由真实 sqlcipher 检验)。
"""

import unittest

from support import qqnt

from cli.keyscan.verify import Algo, detect_algo, hmac_algorithm

__all__ = []

_KEY = b"rawkey0123456!@#"
_DIGESTS = ("sha1", "sha256", "sha512")


class DetectAlgoTests(unittest.TestCase):
    def test_right_passphrase_reports_the_algorithms_used(self) -> None:
        for page in _DIGESTS:
            for kdf in _DIGESTS:
                with self.subTest(page=page, kdf=kdf):
                    self.assertEqual(detect_algo(qqnt.empty_encrypted_database(_KEY, page, kdf), _KEY), Algo(page=page, kdf=kdf))

    def test_wrong_passphrase_matches_nothing(self) -> None:
        database = qqnt.empty_encrypted_database(_KEY)
        # 不取「末尾补 \x00」作反例: HMAC 把短密钥按零填充，它与原口令等价
        for wrong in (b"rawkey0123456!@$", _KEY[:-1], _KEY + b"0", b""):
            with self.subTest(wrong=wrong):
                self.assertIsNone(detect_algo(database, wrong))

    def test_tampered_page_matches_nothing(self) -> None:
        database = bytearray(qqnt.empty_encrypted_database(_KEY))
        database[qqnt.HEADER_SIZE + 100] ^= 0x01
        self.assertIsNone(detect_algo(bytes(database), _KEY))

    def test_misleading_header_marker_does_not_change_the_result(self) -> None:
        # 文件头里的算法标记只用来决定先试哪种，标记与实际不符时仍须得出实际的算法
        plain = qqnt.plain_database(lambda conn: None, page_hmac="sha1")
        header = b"QQ_NT DB\x00HMAC_SHA512".ljust(qqnt.HEADER_SIZE, b"\x00")
        self.assertEqual(detect_algo(qqnt.encrypt_database(plain, _KEY, page_hmac="sha1", header=header), _KEY), Algo(page="sha1", kdf="sha512"))

    def test_file_shorter_than_header_plus_one_page(self) -> None:
        database = qqnt.empty_encrypted_database(_KEY)
        for size in (0, qqnt.HEADER_SIZE, len(database) - 1):
            with self.subTest(size=size):
                self.assertIsNone(detect_algo(database[:size], _KEY))


class HmacAlgorithmTests(unittest.TestCase):
    def test_names_follow_the_page_digest(self) -> None:
        # 这两个名字是 decrypt_db.py -k 接受的算法名，kdf 不影响
        self.assertEqual(hmac_algorithm(Algo(page="sha1", kdf="sha512")), "HMAC_SHA1")
        self.assertEqual(hmac_algorithm(Algo(page="sha512", kdf="sha1")), "HMAC_SHA512")


if __name__ == "__main__":
    unittest.main()
