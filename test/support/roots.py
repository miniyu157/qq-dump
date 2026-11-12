"""三种平台的 QQ 数据根目录样本，以及由文档公式直接算出的期望密钥。

目录结构依据 README「平台与数据」；Android 的密钥公式出自 QQBackup 的公开分析 (QQDecrypt):
  nt 库     md5(md5(uid) + 文件头中 QQ_NT DB 标记后的 8 位 rand)
  gpro 库   md5(md5(salt) + md5(md5(uin) + md5(sha1(uin))))，salt 取自文件头
  账号目录  nt_qq_ + md5(md5(uid) + "nt_kernel")
"""

import hashlib
import sqlite3
from pathlib import Path

from support import qqnt
from support.profile import populate_profile

__all__ = ["GPRO_SALT", "RAND", "account_dir_name", "android_account", "android_gpro_key", "android_nt_key", "android_sample_account", "gpro_header", "linux_accounts", "nt_header", "windows_account", "write_login_db"]

RAND = "Ab3dE5gH"
GPRO_SALT = b"0123456789abcdef"


def _md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


def android_nt_key(uid: str, rand: str) -> str:
    return _md5(_md5(uid) + rand)


def android_gpro_key(uin: str, salt: bytes) -> str:
    seed = _md5(_md5(uin) + _md5(hashlib.sha1(uin.encode()).digest()))
    return _md5(_md5(salt) + seed)


def account_dir_name(uid: str) -> str:
    return "nt_qq_" + _md5(_md5(uid) + "nt_kernel")


def nt_header(rand: str | None) -> bytes:
    """nt 库的 1024 字节明文头；rand 为 None 时不写 QQ_NT DB 标记。"""
    body = b"" if rand is None else b"QQ_NT DB\x00" + rand.encode() + b"\x00"
    return body.ljust(qqnt.HEADER_SIZE, b"\x00")


def gpro_header(salt: bytes | None) -> bytes:
    """gpro 库的 1024 字节明文头；salt 为 None 时写入长度不符的盐值。"""
    salt_part = (4).to_bytes(4, "little") + b"bad!" if salt is None else len(salt).to_bytes(4, "little") + salt
    return (b"Guild DB v1.0.0" + salt_part).ljust(qqnt.HEADER_SIZE, b"\x00")


def android_account(root: Path, user: str, uin: str, uid: str) -> Path:
    """在 Android 布局的 root 下建账号标记与数据库目录，返回数据库目录。"""
    qq_path = root / "data" / "user" / user / "com.tencent.mobileqq"
    marks = qq_path / "files" / "uid"
    marks.mkdir(parents=True, exist_ok=True)
    (marks / f"{uin}###{uid}").touch()
    db_dir = qq_path / "databases" / "nt_db" / account_dir_name(uid)
    db_dir.mkdir(parents=True)
    return db_dir


def android_sample_account(root: Path, user: str, uin: str, uid: str, *, extra_friends: int = 0) -> Path:
    """在 Android 布局的 root 下建一个数据库可以真实解密的账号，返回数据库目录。

    密钥由文件头与文档公式决定: profile_info.db (内容见 support.profile) 与 nt_msg.db 用 nt 密钥、HMAC_SHA1，
    gpro_v1-6_<uid>.db 用 gpro 密钥、HMAC_SHA512；另有一个带 QQ 文件头的明文库 plain.db。
    """
    def messages(conn: sqlite3.Connection) -> None:
        conn.execute('CREATE TABLE c2c_msg_table ("40001" INTEGER, "40800" BLOB)')
        conn.execute("INSERT INTO c2c_msg_table VALUES (1, x'aaea1505')")

    db_dir = android_account(root, user, uin, uid)
    nt_key = android_nt_key(uid, RAND).encode()
    profile = qqnt.plain_database(lambda conn: populate_profile(conn, extra_friends=extra_friends))
    (db_dir / "profile_info.db").write_bytes(qqnt.encrypt_database(profile, nt_key, header=nt_header(RAND)))
    (db_dir / "nt_msg.db").write_bytes(qqnt.encrypt_database(qqnt.plain_database(messages), nt_key, header=nt_header(RAND)))
    gpro = qqnt.plain_database(messages, page_hmac="sha512")
    (db_dir / f"gpro_v1-6_{uid}.db").write_bytes(qqnt.encrypt_database(gpro, android_gpro_key(uin, GPRO_SALT).encode(), page_hmac="sha512", header=gpro_header(GPRO_SALT)))
    (db_dir / "plain.db").write_bytes(nt_header(RAND) + qqnt.plain_database(messages))
    return db_dir


def write_login_db(path: Path, accounts: list[tuple[str, str, str]]) -> None:
    """在 path 写出以 QQ 内置口令加密的 login.db，accounts 每项为 (uin, uid, 昵称)；按需创建所在目录。"""
    def populate(conn: sqlite3.Connection) -> None:
        conn.execute('CREATE TABLE login_table ("1000" TEXT, "1001" TEXT, "1007" TEXT)')
        conn.executemany("INSERT INTO login_table VALUES (?, ?, ?)", accounts)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(qqnt.encrypt_database(qqnt.plain_database(populate), qqnt.PRE_LOGIN_KEY))


def windows_account(root: Path, uin: str, key: bytes | None, *, page_hmac: str = "sha1", kdf: str = "sha512") -> Path:
    """在 Windows 布局的 root 下建账号 <uin>/nt_qq/nt_db，返回该目录。

    key 不为 None 时放入可用它解开的 settings.db；另有一个 10 字节的 nt_msg.db 占位。
    """
    db_dir = root / uin / "nt_qq" / "nt_db"
    db_dir.mkdir(parents=True)
    if key is not None:
        (db_dir / "settings.db").write_bytes(qqnt.empty_encrypted_database(key, page_hmac, kdf))
    (db_dir / "nt_msg.db").write_bytes(b"x" * 10)
    return db_dir


def linux_accounts(root: Path, accounts: list[tuple[str, str, str, bytes | None]], *, nested: bool = False) -> dict[str, Path]:
    """在 Linux 布局的 root 下建 login.db 与各账号目录，返回 uin -> 数据库目录。

    accounts 每项为 (uin, uid, 昵称, 密钥)；密钥不为 None 时该账号有可用它解开的 settings.db。
    nested 为真时 login.db 放在 nt_qq/global/nt_db，否则放在 global/nt_db。
    """
    write_login_db(root / ("nt_qq/global/nt_db" if nested else "global/nt_db") / "login.db", [(uin, uid, nick) for uin, uid, nick, _ in accounts])

    db_dirs = {}
    for uin, uid, _, key in accounts:
        db_dir = root / account_dir_name(uid) / "nt_db"
        db_dir.mkdir(parents=True)
        if key is not None:
            (db_dir / "settings.db").write_bytes(qqnt.empty_encrypted_database(key))
        (db_dir / "nt_msg.db").write_bytes(b"x" * 10)
        db_dirs[uin] = db_dir
    return db_dirs
