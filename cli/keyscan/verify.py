"""SQLCipher 第 1 页 HMAC 校验与算法探测，判断某个 raw_key 能否解开某个数据库。

QQ NT 数据库是 SQLCipher v4 流，页 HMAC 与 KDF 的摘要算法不固定，须对小库
(settings.db) 暴力探测一次再复用。校验只重算第 1 页密文上的 HMAC，不做 AES 解密，
因此整模块只依赖 hashlib 与 hmac。

仅覆盖启用了页 HMAC 的库 (QQ NT 的全部 nt_db 库均属此类)；关闭页 HMAC 的库需 AES
解密后比对文件头，本模块不处理，detect_algo 对其返回 None。

调用顺序: 先用已知 raw_key 对 settings.db 调 detect_algo 得到 Algo，再对其余库复用。
"""

import hashlib
import hmac
from typing import NamedTuple

__all__ = ["Algo", "detect_algo", "hmac_algorithm"]

_HEADER_SIZE = 1024
_PAGE_SIZE = 4096
_SALT_SIZE = 16
_IV_SIZE = 16
_KDF_ITER = 4000
_HMAC_KDF_ITER = 2
# SQLCipher 默认掩码: HMAC 盐 = 页盐逐字节异或 0x3A
_HMAC_MASK = 0x3A

# 摘要名 -> 字节长度; 同时作为页 HMAC 与 KDF 的候选算法集
_DIGEST_SIZE = {"sha1": 20, "sha256": 32, "sha512": 64}
# QQ 现网库的 KDF 实测为 SHA512，放首位让正确 raw_key 少算几轮 PBKDF2
_KDF_ORDER = ("sha512", "sha1", "sha256")
# 页 HMAC 的默认尝试顺序，detect_algo 会据文件头标记把命中的算法提前
_PAGE_ORDER = ("sha1", "sha256", "sha512")

# 摘要名 -> decrypt_db.py 的 -k 算法名; decrypt_db.py 仅支持 SHA1 与 SHA512
_HMAC_NAME = {"sha1": "HMAC_SHA1", "sha512": "HMAC_SHA512", "sha256": "HMAC_SHA256"}


class Algo(NamedTuple):
    """探测出的算法对: page 为页 HMAC 摘要名, kdf 为 PBKDF2 摘要名, 均为 _DIGEST_SIZE 的键。"""

    page: str
    kdf: str


def hmac_algorithm(algo: Algo) -> str:
    """返回 algo.page 对应的 decrypt_db.py -k 算法名 (如 HMAC_SHA1)。"""
    return _HMAC_NAME[algo.page]


def _page_order(db_bytes: bytes) -> tuple[str, ...]:
    """按文件头明文中的 HMAC_SHAxxx 标记把命中的页算法提前，其余保持默认顺序。"""
    header = db_bytes[:_HEADER_SIZE]
    for name, digest in (("HMAC_SHA512", "sha512"), ("HMAC_SHA256", "sha256"), ("HMAC_SHA1", "sha1")):
        if name.encode() in header:
            return (digest, *(other for other in _PAGE_ORDER if other != digest))
    return _PAGE_ORDER


def detect_algo(db_bytes: bytes, passphrase: bytes) -> Algo | None:
    """暴力探测能用 passphrase 解开 db_bytes 的 (page, kdf) 算法对；都不匹配时返回 None。

    passphrase 为 raw_key 字节；校验用第 1 页密文上的 HMAC，错误口令对任何算法对都
    不会命中。按 kdf 外层缓存派生密钥、页算法按文件头标记优先，只为少算 PBKDF2，
    判定结果与遍历顺序无关。
    """
    if len(db_bytes) < _HEADER_SIZE + _PAGE_SIZE:
        return None
    page1 = db_bytes[_HEADER_SIZE:_HEADER_SIZE + _PAGE_SIZE]
    salt = page1[:_SALT_SIZE]
    hmac_salt = bytes(byte ^ _HMAC_MASK for byte in salt)
    page_order = _page_order(db_bytes)

    for kdf in _KDF_ORDER:
        aes_key = hashlib.pbkdf2_hmac(kdf, passphrase, salt, _KDF_ITER, 32)
        hmac_key = hashlib.pbkdf2_hmac(kdf, aes_key, hmac_salt, _HMAC_KDF_ITER, 32)
        for page in page_order:
            digest_size = _DIGEST_SIZE[page]
            reserve = (_IV_SIZE + digest_size + 15) // 16 * 16
            data_end = _PAGE_SIZE - reserve
            message = page1[_SALT_SIZE:data_end] + page1[data_end:data_end + _IV_SIZE] + (1).to_bytes(4, "little")
            stored = page1[data_end + _IV_SIZE:data_end + _IV_SIZE + digest_size]
            computed = hmac.new(hmac_key, message, page).digest()
            if hmac.compare_digest(computed, stored):
                return Algo(page=page, kdf=kdf)
    return None
