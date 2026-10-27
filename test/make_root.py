#!/usr/bin/env python3
"""按 cli/ 的约定在脚本同级的 root/ 下生成 QQ 数据目录，测试使用。

root/ 已存在时拒绝运行；需要重新生成时手动删除 root/。
先在同级临时目录内生成，全部成功后再改名为 root/，中途失败不会留下半份数据。

账号场景:
  user 0  10001  只有空的数据库目录，rand 为空
  user 0  10002  有数据库但文件头缺少 QQ_NT DB 标记，rand 为空；gpro 文件头无法识别盐值
  user 10 10003  文件五花八门: 可正常解密的 profile_info.db 与 nt_msg.db、错误密钥、未加密、
                 空文件、仅文件头、可解密的 gpro 库，以及不参与 glob 的 readme.txt
  user 0  异常 uid 标记: 缺少 ### 分隔、uin 为空、uid 为空，均不建数据库目录
"""

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "root"

# 明文头部长度，decrypt_db.py 解密前跳过这一段
HEADER_SIZE = 1024

RAND = "Ab3dE5gH"
GPRO_SALT = b"0123456789abcdef"


def md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


def nt_db_dir(qq_path: Path, uid: str) -> Path:
    return qq_path / "databases" / "nt_db" / f"nt_qq_{md5(md5(uid) + 'nt_kernel')}"


def nt_key(uid: str, rand: str) -> str:
    return md5(md5(uid) + rand)


def gpro_key(uin: str, salt: bytes) -> str:
    uin_bytes = uin.encode()
    user_seed = md5(md5(uin_bytes) + md5(hashlib.sha1(uin_bytes).digest()))
    return md5(md5(salt) + user_seed)


def nt_header(rand: str | None) -> bytes:
    """rand 为 None 时不写 QQ_NT DB 标记"""
    body = b"" if rand is None else b"QQ_NT DB\x00" + rand.encode() + b"\x00"
    return body.ljust(HEADER_SIZE, b"\x00")


def gpro_header(salt: bytes | None) -> bytes:
    """salt 为 None 时写入长度不符的盐值，get_keys.py 会判定为无法识别"""
    salt_part = (16).to_bytes(4, "little") + salt if salt else (4).to_bytes(4, "little") + b"bad!"
    return (b"Guild DB v1.0.0" + salt_part).ljust(HEADER_SIZE, b"\x00")


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def field(number: int, value: int | bytes) -> bytes:
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def write_profile(path: Path, owner_uid: str, owner_uin: int) -> None:
    """字段号与 schema/ 的映射一致，覆盖好友、已删除好友、机器人、分组与密友关系"""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE buddy_list ("1000" TEXT);
        CREATE TABLE profile_info_adelie ("1000" TEXT);
        CREATE TABLE category_list_v2 ("1000" TEXT, "25011" BLOB);
        CREATE TABLE profile_info_v6 (
            "1000" TEXT, "1001" TEXT, "1002" INTEGER, "20001" INTEGER, "20002" TEXT,
            "20006" INTEGER, "20007" INTEGER, "20008" INTEGER, "20009" TEXT, "20011" TEXT,
            "20014" INTEGER, "20048" INTEGER, "20070" INTEGER, "20072" BLOB, "24103" INTEGER
        );
    """)
    conn.executemany("INSERT INTO buddy_list VALUES (?)", [("u_friend_a",), ("u_bot_c",)])
    conn.execute("INSERT INTO profile_info_adelie VALUES (?)", ("u_bot_c",))
    for group_id, name in ((0, "我的好友"), (1, "同学")):
        group = field(25011, field(25007, group_id) + field(25008, name.encode()))
        conn.execute("INSERT INTO category_list_v2 VALUES (?, ?)", (owner_uid, group))
    lovers = field(20072, field(20074, 1))
    conn.executemany("INSERT INTO profile_info_v6 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (owner_uid, None, owner_uin, 0, "主人", 2000, 1, 1, None, "签名", 1, 0, 0, None, 25),
        ("u_friend_a", "qid_a", 20001, 1700000000, "好友甲", 2001, 2, 3, "备注甲", None, 2, 1, 1314, lovers, 24),
        ("u_deleted_b", None, 20002, 1690000000, "已删除乙", 0, 0, 0, None, None, 0, 0, 0, None, 0),
        ("u_bot_c", None, 20003, 1680000000, "机器人丙", 0, 0, 0, None, None, 255, 0, 0, None, 0),
    ])
    conn.commit()
    conn.close()


def write_msg(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE c2c_msg_table ("40001" INTEGER, "40800" BLOB)')
    conn.execute("INSERT INTO c2c_msg_table VALUES (?, ?)", (1, field(45101, b"hello")))
    conn.commit()
    conn.close()


def encrypt(plain: Path, target: Path, header: bytes, key: str, hmac_algorithm: str) -> None:
    """按 decrypt_db.py 的参数加密，再在前面拼上明文头部"""
    body = target.with_suffix(".body")
    sql = "\n".join([
        f"PRAGMA key = '{key}';",
        "PRAGMA kdf_iter = 4000;",
        f"PRAGMA cipher_hmac_algorithm = {hmac_algorithm};",
        "PRAGMA cipher_page_size = 4096;",
        f"ATTACH DATABASE '{plain}' AS plaintext KEY '';",
        "SELECT sqlcipher_export('main', 'plaintext');",
        "DETACH DATABASE plaintext;",
    ]) + "\n"
    subprocess.run(["sqlcipher", str(body)], input=sql.encode(), stdout=subprocess.DEVNULL, check=True)
    target.write_bytes(header + body.read_bytes())
    body.unlink()


def account(root: Path, user: str, uin: str, uid: str) -> tuple[Path, Path]:
    """建账号标记，返回 (QQ 应用目录, 数据库目录)"""
    qq_path = root / "data" / "user" / user / "com.tencent.mobileqq"
    marks = qq_path / "files" / "uid"
    marks.mkdir(parents=True, exist_ok=True)
    (marks / f"{uin}###{uid}").touch()
    db_dir = nt_db_dir(qq_path, uid)
    db_dir.mkdir(parents=True)
    return qq_path, db_dir


def build(root: Path, work: Path) -> None:
    profile, msg = work / "profile.plain", work / "msg.plain"

    _, db_dir = account(root, "0", "10001", "u_AAAAAAAAAAAAAAAAAAAAAA")

    uin, uid = "10002", "u_BBBBBBBBBBBBBBBBBBBBBB"
    _, db_dir = account(root, "0", uin, uid)
    write_profile(profile, uid, int(uin))
    write_msg(msg)
    encrypt(profile, db_dir / "profile_info.db", nt_header(None), nt_key(uid, RAND), "HMAC_SHA1")
    encrypt(msg, db_dir / "nt_msg.db", nt_header(None), nt_key(uid, RAND), "HMAC_SHA1")
    (db_dir / f"gpro_v1-6_{uid}.db").write_bytes(gpro_header(None))
    profile.unlink()
    msg.unlink()

    uin, uid = "10003", "u_CCCCCCCCCCCCCCCCCCCCCC"
    _, db_dir = account(root, "10", uin, uid)
    key = nt_key(uid, RAND)
    write_profile(profile, uid, int(uin))
    write_msg(msg)
    encrypt(profile, db_dir / "profile_info.db", nt_header(RAND), key, "HMAC_SHA1")
    encrypt(msg, db_dir / "nt_msg.db", nt_header(RAND), key, "HMAC_SHA1")
    encrypt(msg, db_dir / "wrong_key.db", nt_header(RAND), md5("wrong"), "HMAC_SHA1")
    encrypt(msg, db_dir / f"gpro_v1-6_{uid}.db", gpro_header(GPRO_SALT), gpro_key(uin, GPRO_SALT), "HMAC_SHA512")
    (db_dir / "plain.db").write_bytes(nt_header(RAND) + msg.read_bytes())
    (db_dir / "empty.db").touch()
    (db_dir / "header_only.db").write_bytes(nt_header(RAND))
    (db_dir / "readme.txt").write_text("不是数据库，get_keys.py 与 decrypt_db.py 只匹配 *.db\n", encoding="utf-8")

    marks = root / "data" / "user" / "0" / "com.tencent.mobileqq" / "files" / "uid"
    for name in ("10004", "###u_EEEEEEEEEEEEEEEEEEEEEE", "10006###"):
        (marks / name).touch()


def main() -> None:
    if ROOT.exists():
        sys.exit(f"错误: 文件夹已存在 {ROOT}")
    if shutil.which("sqlcipher") is None:
        sys.exit("错误: 生成加密数据库需要 sqlcipher")

    staging = Path(tempfile.mkdtemp(prefix=".root-", dir=ROOT.parent))
    work = Path(tempfile.mkdtemp(prefix=".work-", dir=ROOT.parent))
    try:
        build(staging, work)
        staging.rename(ROOT)
    finally:
        shutil.rmtree(work)
        if staging.exists():
            shutil.rmtree(staging)
    print(ROOT)


if __name__ == "__main__":
    main()
