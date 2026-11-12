"""cli.keyscan.aes: AES-256-CBC 解密。

判定基准: FIPS-197 附录 C.3 与 SP 800-38A F.2.6 的标准向量。
"""

import unittest

from cli.keyscan.aes import aes256_cbc_decrypt

__all__ = []


class StandardVectorTests(unittest.TestCase):
    def test_fips197_single_block(self) -> None:
        plain = aes256_cbc_decrypt(bytes(range(32)), bytes(16), bytes.fromhex("8ea2b7ca516745bfeafc49904b496089"))
        self.assertEqual(plain.hex(), "00112233445566778899aabbccddeeff")

    def test_sp800_38a_cbc_chain(self) -> None:
        key = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
        cipher = bytes.fromhex("f58c4c04d6e5f1ba779eabfb5f7bfbd69cfc4e967edb808d679f777bc6702c7d39f23369a9d9bacfa530e26304231461b2eb05e2c39be9fcda6c19078c6a9d1b")
        plain = aes256_cbc_decrypt(key, bytes(range(16)), cipher)
        self.assertEqual(plain.hex(), "6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e5130c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710")

    def test_empty_ciphertext(self) -> None:
        self.assertEqual(aes256_cbc_decrypt(bytes(32), bytes(16), b""), b"")


class ArgumentTests(unittest.TestCase):
    def test_rejects_wrong_sizes(self) -> None:
        wrong = {"16 字节密钥": (bytes(16), bytes(16), bytes(16)), "8 字节 IV": (bytes(32), bytes(8), bytes(16)), "密文不是整块": (bytes(32), bytes(16), bytes(17))}
        for reason, (key, iv, cipher) in wrong.items():
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                aes256_cbc_decrypt(key, iv, cipher)


if __name__ == "__main__":
    unittest.main()
