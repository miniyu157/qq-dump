"""QQ NT 数据库样本的构造: 标准库 sqlite3 写出明文库，再按 SQLCipher 4 的页格式逐页加密。

格式依据 SQLite 文件格式文档与 SQLCipher 的设计说明，不引用被测代码:
  文件      1024 字节 QQ 明文头，其后为 4096 字节的页
  密钥      AES 密钥 = PBKDF2(口令, salt, 4000 轮)；HMAC 密钥 = PBKDF2(AES 密钥, salt 逐字节异或 0x3A, 2 轮)
  页        密文 | 16 字节 IV | 页 HMAC | 补零；第 1 页开头 16 字节是 salt，不加密
  页 HMAC   覆盖密文、IV 与小端 4 字节页号
  WAL       文件头与帧头保持明文，每帧一页密文；校验和按写入的内容 (密文) 滚动计算
构造出的库在契约层由真实 sqlcipher 解开，以此反过来检验本模块。
"""

import hashlib
import hmac
import sqlite3
from collections.abc import Callable
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from support.aes import aes256_cbc_encrypt

__all__ = ["HEADER_SIZE", "PAGE_SIZE", "PRE_LOGIN_KEY", "WalFrame", "empty_encrypted_database", "encrypt_database", "encrypt_wal", "plain_database", "plain_database_with_wal", "reserve_size"]

HEADER_SIZE = 1024
PAGE_SIZE = 4096
# QQ 客户端内置的 login.db 口令，出自 QQBackup 的公开分析，与账号无关
PRE_LOGIN_KEY = b"BD156D6710D54D8782F4"

_SALT = bytes(range(0x30, 0x40))
_DIGEST_SIZE = {"sha1": 20, "sha256": 32, "sha512": 64}
_WAL_HEADER = 32
_FRAME_HEADER = 24

Populate = Callable[[sqlite3.Connection], None]


class WalFrame(NamedTuple):
    """WAL 的一帧: 页号、提交标记 (非 0 表示事务在此提交，值为提交后的库页数)、帧头里的 salt 与明文页。"""

    page_number: int
    commit: int
    salt: bytes
    page: bytes


def reserve_size(page_hmac: str) -> int:
    """每页尾部的保留字节: IV 加页 HMAC 摘要，向 16 字节对齐。"""
    return (16 + _DIGEST_SIZE[page_hmac] + 15) // 16 * 16


def _empty_sqlite(reserve: int) -> bytes:
    """只含一张空 sqlite_master 页的 SQLite 文件，每页尾部保留 reserve 字节。

    SQLite 没有设置保留字节的 SQL 接口，只认文件头第 20 字节；从这个头开始建表，新分配的页都会留出同样的空间。
    """
    page = bytearray(PAGE_SIZE)
    page[:16] = b"SQLite format 3\x00"
    page[16:18] = PAGE_SIZE.to_bytes(2, "big")
    page[18] = page[19] = 1  # 回滚日志模式
    page[20] = reserve
    page[21], page[22], page[23] = 64, 32, 32
    page[28:32] = (1).to_bytes(4, "big")  # 库页数
    page[44:48] = (4).to_bytes(4, "big")  # schema 格式
    page[56:60] = (1).to_bytes(4, "big")  # UTF-8
    page[100] = 0x0D  # 第 1 页是空的叶子表页
    page[105:107] = (PAGE_SIZE - reserve).to_bytes(2, "big")  # cell 内容区起点 = 可用区末尾
    return bytes(page)


def plain_database(populate: Populate, *, page_hmac: str = "sha1") -> bytes:
    """返回由 populate(conn) 建表并写入数据的明文库；页尾留有 page_hmac 对应的保留字节，可交给 encrypt_database。"""
    with TemporaryDirectory() as directory:
        path = Path(directory) / "plain.db"
        path.write_bytes(_empty_sqlite(reserve_size(page_hmac)))
        conn = sqlite3.connect(path)
        try:
            populate(conn)
            conn.commit()
        finally:
            conn.close()
        return path.read_bytes()


def plain_database_with_wal(populate_main: Populate, populate_wal: Populate, *, page_hmac: str = "sha1") -> tuple[bytes, bytes]:
    """返回 (主文件, -wal 文件) 的明文字节: populate_main 的数据落在主文件，populate_wal 的数据只在 WAL 中。

    populate_wal 内每次 conn.commit() 产生一个事务，末尾未提交的改动由本函数提交。
    """
    with TemporaryDirectory() as directory:
        path = Path(directory) / "plain.db"
        path.write_bytes(_empty_sqlite(reserve_size(page_hmac)))
        conn = sqlite3.connect(path)
        try:
            populate_main(conn)
            conn.commit()
            conn.execute("PRAGMA journal_mode=WAL").fetchall()
            conn.execute("PRAGMA wal_autocheckpoint=0").fetchall()
            populate_wal(conn)
            conn.commit()
            # 连接关闭时会把 WAL 合并回主文件，须在关闭前取走两个文件
            return path.read_bytes(), path.with_name("plain.db-wal").read_bytes()
        finally:
            conn.close()


def _keys(passphrase: bytes, kdf: str, salt: bytes) -> tuple[bytes, bytes]:
    aes_key = hashlib.pbkdf2_hmac(kdf, passphrase, salt, 4000, 32)
    hmac_key = hashlib.pbkdf2_hmac(kdf, aes_key, bytes(byte ^ 0x3A for byte in salt), 2, 32)
    return aes_key, hmac_key


def _encrypt_page(page: bytes, page_number: int, keys: tuple[bytes, bytes], page_hmac: str, salt: bytes, nonce: int) -> bytes:
    aes_key, hmac_key = keys
    skip = len(salt) if page_number == 1 else 0
    # IV 只需各页各次写入互不相同，用页号与序号派生，使样本可复现
    iv = hashlib.md5(f"iv {page_number} {nonce}".encode()).digest()
    ciphertext = aes256_cbc_encrypt(aes_key, iv, page[skip:PAGE_SIZE - reserve_size(page_hmac)])
    mac = hmac.new(hmac_key, ciphertext + iv + page_number.to_bytes(4, "little"), page_hmac).digest()
    stored = (salt if page_number == 1 else b"") + ciphertext + iv + mac
    return stored + bytes(PAGE_SIZE - len(stored))


def encrypt_database(plain: bytes, passphrase: bytes, *, page_hmac: str = "sha1", kdf: str = "sha512", header: bytes = bytes(HEADER_SIZE), salt: bytes = _SALT) -> bytes:
    """把 plain_database 得到的明文库加密为 QQ NT 的库文件: header 之后逐页为密文。

    page_hmac 与 kdf 为 sha1、sha256 或 sha512，page_hmac 须与建库时的一致；header 为文件开头的 QQ 明文头。
    """
    keys = _keys(passphrase, kdf, salt)
    pages = [plain[start:start + PAGE_SIZE] for start in range(0, len(plain), PAGE_SIZE)]
    return header + b"".join(_encrypt_page(page, number, keys, page_hmac, salt, 0) for number, page in enumerate(pages, 1))


@cache
def empty_encrypted_database(passphrase: bytes, page_hmac: str = "sha1", kdf: str = "sha512") -> bytes:
    """一个不含任何表的加密库，足以充当验证口令用的 settings.db。"""
    return encrypt_database(_empty_sqlite(reserve_size(page_hmac)), passphrase, page_hmac=page_hmac, kdf=kdf)


def _checksum(data: bytes, seed: tuple[int, int], order: str) -> tuple[int, int]:
    """SQLite WAL 的滚动校验和: 每 8 字节取两个 32 位字，交替累加。"""
    first, second = seed
    for start in range(0, len(data), 8):
        first = (first + int.from_bytes(data[start:start + 4], order) + second) & 0xFFFFFFFF
        second = (second + int.from_bytes(data[start + 4:start + 8], order) + first) & 0xFFFFFFFF
    return first, second


def encrypt_wal(plain_wal: bytes, passphrase: bytes, *, page_hmac: str = "sha1", kdf: str = "sha512", salt: bytes = _SALT, edit: Callable[[list[WalFrame]], list[WalFrame]] | None = None) -> bytes:
    """把 plain_database_with_wal 得到的明文 -wal 加密为与 encrypt_database 配套的 -wal 文件。

    edit 在加密前改写帧序列，用来构造未提交的尾帧、salt 不符的旧帧等情形；校验和在改写之后重新计算。
    """
    keys = _keys(passphrase, kdf, salt)
    # 文件头的 magic 末位指明校验和的字序: 0x377f0682 为小端，0x377f0683 为大端
    order = "big" if plain_wal[3] & 1 else "little"
    frame_size = _FRAME_HEADER + PAGE_SIZE
    frames = []
    for start in range(_WAL_HEADER, len(plain_wal) - frame_size + 1, frame_size):
        head = plain_wal[start:start + _FRAME_HEADER]
        frames.append(WalFrame(int.from_bytes(head[0:4], "big"), int.from_bytes(head[4:8], "big"), head[8:16], plain_wal[start + _FRAME_HEADER:start + frame_size]))
    if edit is not None:
        frames = edit(frames)

    running = _checksum(plain_wal[:24], (0, 0), order)
    output = bytearray(plain_wal[:24] + running[0].to_bytes(4, "big") + running[1].to_bytes(4, "big"))
    for index, frame in enumerate(frames):
        stored = _encrypt_page(frame.page, frame.page_number, keys, page_hmac, salt, index + 1)
        head = frame.page_number.to_bytes(4, "big") + frame.commit.to_bytes(4, "big")
        running = _checksum(head + stored, running, order)
        output += head + frame.salt + running[0].to_bytes(4, "big") + running[1].to_bytes(4, "big") + stored
    return bytes(output)
