"""解密 login.db 并读取其中缓存的账号 (uin/uid/昵称)。

login.db 是全局库 (与账号无关), 用客户端内置的固定密钥加密, 列出本机登录过的每个账号。
解密全程纯 Python: 剥 1024 字节 QQ 文件头, 逐页 AES-256-CBC 解密 (keyscan.aes), 重建
标准 SQLite 页, 合并 -wal 中尚未 checkpoint 的页, 再写入临时文件以只读方式查询 login_table,
读后即删。不依赖 sqlcipher/openssl, 源文件只读。

Windows 下账号可由目录名枚举, 本模块仅用于补全 uid 与昵称; Linux 下账号目录名是 uid
派生的哈希, 必须经此取得 uid 才能定位账号目录。read_accounts(path) 返回 Account 列表,
文件缺失、解密失败或表缺失时抛 OSError。
"""

import sqlite3
import sys
from pathlib import Path
from typing import NamedTuple

from cli.keyscan import aes, verify
from cli.keyscan.verify import Algo

__all__ = ["Account", "read_accounts"]

# 客户端内置的 login.db 预登录密钥
_PRE_LOGIN_KEY = b"BD156D6710D54D8782F4"

_HEADER_SIZE = 1024
_PAGE_SIZE = 4096
_SALT_SIZE = 16
_IV_SIZE = 16
_KDF_ITER = 4000

_SQLITE_MAGIC = b"SQLite format 3\x00"
_WAL_HDR_SIZE = 32
_WAL_FRAME_HDR_SIZE = 24


class Account(NamedTuple):
    uin: str
    uid: str
    nick: str


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _reserve(algo: Algo) -> int:
    """页尾保留字节 = IV + 页 HMAC 摘要, 向 16 字节对齐。"""
    digest_size = {"sha1": 20, "sha256": 32, "sha512": 64}[algo.page]
    return (_IV_SIZE + digest_size + 15) // 16 * 16


def _derive_key(passphrase: bytes, salt: bytes, algo: Algo) -> bytes:
    import hashlib

    return hashlib.pbkdf2_hmac(algo.kdf, passphrase, salt, _KDF_ITER, 32)


def _decrypt_page(page: bytes, key: bytes, skip: int, reserve: int) -> bytes:
    """解一页: 跳过 skip 字节 (第 1 页为 salt), 末尾 reserve 字节为 IV+HMAC, IV 紧接密文。"""
    enc_len = _PAGE_SIZE - skip - reserve
    ciphertext = page[skip:skip + enc_len]
    iv = page[skip + enc_len:skip + enc_len + _IV_SIZE]
    return aes.aes256_cbc_decrypt(key, iv, ciphertext)


def _plaintext_page(page_num: int, body: bytes) -> bytes:
    """由解密后的页体重建标准 SQLite 页; 第 1 页前 16 字节原为 salt, 恢复 magic 与页大小。"""
    full = bytearray(_PAGE_SIZE)
    if page_num == 1:
        full[:16] = _SQLITE_MAGIC
        take = min(len(body), _PAGE_SIZE - 16)
        full[16:16 + take] = body[:take]
        full[16] = (_PAGE_SIZE >> 8) & 0xFF
        full[17] = _PAGE_SIZE & 0xFF
        # 读写版本号 2 表示 WAL 模式, 打开时会创建 -wal/-shm; WAL 已合并进镜像, 改回 1 (回滚日志)
        full[18] = 1
        full[19] = 1
    else:
        take = min(len(body), _PAGE_SIZE)
        full[:take] = body[:take]
    return bytes(full)


def _decrypt_main(db_bytes: bytes, key: bytes, algo: Algo) -> bytearray:
    """解密主库全部页, 返回标准 SQLite 镜像 (页号从 1 起)。"""
    stream = db_bytes[_HEADER_SIZE:]
    total_pages = len(stream) // _PAGE_SIZE
    reserve = _reserve(algo)
    image = bytearray()
    for page_num in range(1, total_pages + 1):
        off = (page_num - 1) * _PAGE_SIZE
        page = stream[off:off + _PAGE_SIZE]
        skip = _SALT_SIZE if page_num == 1 else 0
        body = _decrypt_page(page, key, skip, reserve)
        image += _plaintext_page(page_num, body)
    return image


def _wal_checksum(seed: tuple[int, int], data: bytes, little_endian: bool) -> tuple[int, int]:
    """SQLite WAL 的滚动校验和: 两个 32 位累加器按 8 字节一组推进; 字序由 WAL magic 决定。"""
    s0, s1 = seed
    order = "little" if little_endian else "big"
    for off in range(0, len(data), 8):
        s0 = (s0 + int.from_bytes(data[off:off + 4], order) + s1) & 0xFFFFFFFF
        s1 = (s1 + int.from_bytes(data[off + 4:off + 8], order) + s0) & 0xFFFFFFFF
    return s0, s1


def _valid_frames(wal: bytes) -> int:
    """返回 WAL 开头连续有效的帧数, 与 SQLite 恢复 WAL 的规则一致。

    帧的 salt 须与 WAL 头相同 (否则是 checkpoint 重置前遗留的旧帧), 且校验和链连续成立;
    校验和按存储内容 (即密文) 计算。遇到第一个无效帧即停止, 其后的帧一律不采用。
    WAL 头无效 (magic、页大小或头校验和不符) 时返回 0。
    """
    if len(wal) < _WAL_HDR_SIZE:
        return 0
    magic = int.from_bytes(wal[0:4], "big")
    if magic not in (0x377F0682, 0x377F0683):
        return 0
    little_endian = magic == 0x377F0682
    if int.from_bytes(wal[8:12], "big") != _PAGE_SIZE:
        return 0
    running = _wal_checksum((0, 0), wal[:24], little_endian)
    if running != (int.from_bytes(wal[24:28], "big"), int.from_bytes(wal[28:32], "big")):
        return 0

    salt = wal[16:24]
    frame_size = _WAL_FRAME_HDR_SIZE + _PAGE_SIZE
    total = (len(wal) - _WAL_HDR_SIZE) // frame_size
    for i in range(total):
        off = _WAL_HDR_SIZE + i * frame_size
        header = wal[off:off + _WAL_FRAME_HDR_SIZE]
        if header[8:16] != salt:
            return i
        running = _wal_checksum(running, header[:8] + wal[off + _WAL_FRAME_HDR_SIZE:off + frame_size], little_endian)
        if running != (int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")):
            return i
    return total


def _merge_wal(image: bytearray, wal: bytes, key: bytes, algo: Algo) -> int:
    """把 -wal 中有效帧的页解密后覆盖到内存镜像, 返回合并的页数。

    WAL 帧头与库头保持明文, 每帧携带一页密文 (第 1 页仍带 16 字节 salt 前缀), AES 密钥
    与主库相同。只采用开头连续有效的帧 (见 _valid_frames), 并只回放到其中最后一个提交帧
    (帧头 commit 字段非 0), 丢弃未提交的尾帧; 提交帧的 commit 值给出该事务后的库页数,
    用于把镜像裁剪到正确大小。同页多次写入时只有最后一次生效。
    """
    reserve = _reserve(algo)
    frame_size = _WAL_FRAME_HDR_SIZE + _PAGE_SIZE
    frames = _valid_frames(wal)

    last_commit = -1
    db_pages = 0
    for i in range(frames):
        off = _WAL_HDR_SIZE + i * frame_size
        commit = int.from_bytes(wal[off + 4:off + 8], "big")
        if commit:
            last_commit = i
            db_pages = commit
    if last_commit < 0:
        return 0

    # 先按页号留最末帧, 避免重复解密 (纯 Python AES 较慢)
    latest_frame: dict[int, int] = {}
    for i in range(last_commit + 1):
        off = _WAL_HDR_SIZE + i * frame_size
        page_num = int.from_bytes(wal[off:off + 4], "big")
        if page_num >= 1:
            latest_frame[page_num] = i

    for page_num, i in latest_frame.items():
        off = _WAL_HDR_SIZE + i * frame_size
        page = wal[off + _WAL_FRAME_HDR_SIZE:off + frame_size]
        skip = _SALT_SIZE if page_num == 1 else 0
        body = _decrypt_page(page, key, skip, reserve)
        plain = _plaintext_page(page_num, body)
        end = page_num * _PAGE_SIZE
        if len(image) < end:
            image.extend(b"\x00" * (end - len(image)))
        image[(page_num - 1) * _PAGE_SIZE:end] = plain

    # 事务可能缩小数据库; 按最后提交的页数裁剪镜像, 避免残留旧页破坏完整性
    del image[db_pages * _PAGE_SIZE:]
    return len(latest_frame)


def _query_login_table(image: bytes) -> list[Account]:
    """把内存镜像写入临时文件, 以只读方式查询 login_table 的 1000/1001/1007 列。

    不用 sqlite3.deserialize: 新建的 :memory: 连接已初始化 main schema, deserialize 会与
    之冲突, 故写入临时文件再只读打开。文件读后即删。
    """
    import os
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix="qq_login_", suffix=".db")
    os.close(fd)
    try:
        Path(tmp).write_bytes(image)
        conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            rows = conn.execute('SELECT "1000", "1001", "1007" FROM login_table').fetchall()
        finally:
            conn.close()
    finally:
        for leftover in (tmp, f"{tmp}-wal", f"{tmp}-shm", f"{tmp}-journal"):
            try:
                os.unlink(leftover)
            except OSError:
                pass
    return [Account(uin=_to_text(uin), uid=_to_text(uid), nick=_to_text(nick)) for uin, uid, nick in rows]


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def read_accounts(path: Path, *, verbose: bool = False) -> list[Account]:
    """解密 path 处的 login.db (含同名 -wal) 并返回缓存的账号列表。

    用内置预登录密钥探测页 HMAC 与 KDF 的算法组合, 都不匹配时抛 OSError (客户端布局可能变化)。
    文件缺失、算法探测失败或查询失败均抛 OSError。
    """
    try:
        db_bytes = path.read_bytes()
    except OSError as exc:
        raise OSError(f"读取 login.db 失败: {exc}") from exc

    algo = verify.detect_algo(db_bytes, _PRE_LOGIN_KEY)
    if algo is None:
        raise OSError(f"无法解密 login.db: 内置密钥对各种算法组合均不匹配 ({path})")
    if verbose:
        _log(f"get_keys: login.db 算法 page={algo.page} kdf={algo.kdf}")

    salt = db_bytes[_HEADER_SIZE:_HEADER_SIZE + _SALT_SIZE]
    key = _derive_key(_PRE_LOGIN_KEY, salt, algo)
    image = _decrypt_main(db_bytes, key, algo)

    wal_path = path.with_name(path.name + "-wal")
    if wal_path.is_file():
        merged = _merge_wal(image, wal_path.read_bytes(), key, algo)
        if verbose and merged:
            _log(f"get_keys: login.db 合并 -wal 的 {merged} 帧")

    try:
        return _query_login_table(bytes(image))
    except sqlite3.Error as exc:
        raise OSError(f"读取 login_table 失败: {exc}") from exc
