#!/usr/bin/env python3
"""解密 QQ NT 数据库文件。"""

import argparse
import hashlib
import hmac
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# stderr 消息的来源前缀
PROG = Path(__file__).name

# 明文文件头长度与 cipher_page_size
HEADER_SIZE = 1024
PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16

# SQLite 把文件偏移 2^30 所在的整页留给文件锁。QQ 的文件带 1024 字节明文头，留空的是第 262144 页；
# 剥头后 SQLite 改认 262145 为锁页，而这一页存着真实数据，读到即报 database disk image is malformed。
LOCK_PAGE = 0x40000000 // PAGE_SIZE + 1

# HMAC 算法 -> (页尾保留字节, 摘要名, 摘要长度)；保留字节为 IV 加摘要向 16 字节对齐
PAGE_CIPHER = {"HMAC_SHA1": (48, "sha1", 20), "HMAC_SHA512": (80, "sha512", 64)}

KDF_ITER = 4000
HMAC_KDF_ITER = 2

# integrity_check 对锁页的报告，父指针位于某个 cell 或页头的右子指针
LOCK_REF_RE = re.compile(rf"page (\d+) (?:cell (\d+)|(right child)): 2nd reference to page {LOCK_PAGE}\b")


def db_cipher(filename: str, key: str | None, gpro_key: str | None) -> tuple[str, str] | None:
    if filename.startswith("gpro_v1-6_"):
        return (gpro_key, "HMAC_SHA512") if gpro_key else None
    return (key, "HMAC_SHA1") if key else None


def safe_output_path(output: str | Path, out_name: str) -> str:
    base = Path(output).resolve()
    target = (base / out_name).resolve()
    if target == base:
        raise ValueError(f"输出路径不能是输出目录本身: {target}")
    if base not in target.parents:
        raise ValueError(f"输出路径越出输出目录: {target}")
    return str(target)


def run_sqlcipher(db_path: str, key: str, hmac_algorithm: str, statements: list[str]) -> subprocess.CompletedProcess:
    key_sql = key.replace("'", "''")
    sql = "\n".join([
        f"PRAGMA key = '{key_sql}';",
        f"PRAGMA kdf_iter = {KDF_ITER};",
        f"PRAGMA cipher_hmac_algorithm = {hmac_algorithm};",
        f"PRAGMA cipher_page_size = {PAGE_SIZE};",
        *statements,
    ]) + "\n"
    return subprocess.run(["sqlcipher", db_path], input=sql.encode(), capture_output=True, check=False)


def derive_keys(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    """主密钥取自口令与 salt，HMAC 密钥由主密钥与按 SQLCipher 默认掩码 0x3A 异或后的 salt 派生"""
    key = hashlib.pbkdf2_hmac("sha512", passphrase.encode(), salt, KDF_ITER, 32)
    hmac_salt = bytes(byte ^ 0x3A for byte in salt)
    return key, hashlib.pbkdf2_hmac("sha512", key, hmac_salt, HMAC_KDF_ITER, 32)


def page_mac(raw: bytes, pgno: int, hmac_key: bytes, hmac_algorithm: str) -> bytes:
    """页尾摘要覆盖密文、IV 与页号，因此迁页必须重算"""
    reserve, digest, mac_size = PAGE_CIPHER[hmac_algorithm]
    start = SALT_SIZE if pgno == 1 else 0
    return hmac.new(hmac_key, raw[start : PAGE_SIZE - reserve + IV_SIZE] + pgno.to_bytes(4, "little"), digest).digest()[:mac_size]


def aes_cbc(flag: str, key: bytes, iv: bytes, data: bytes) -> bytes:
    argv = ["openssl", "enc", flag, "-aes-256-cbc", "-nopad", "-K", key.hex(), "-iv", iv.hex()]
    return subprocess.run(argv, input=data, capture_output=True, check=True).stdout


def read_page(handle, pgno: int) -> bytes:
    handle.seek((pgno - 1) * PAGE_SIZE)
    return handle.read(PAGE_SIZE)


def write_page(handle, pgno: int, raw: bytes) -> None:
    handle.seek((pgno - 1) * PAGE_SIZE)
    handle.write(raw)


def relocate_lock_page(tmp_path: str, key: str, hmac_algorithm: str) -> None:
    """把锁页上的数据迁到 QQ 留空的前一页，并改写指向它的父指针"""
    # integrity_check 无需自行遍历 b-tree 即可报出父指针位置，代价是多扫一遍全库
    checked = run_sqlcipher(tmp_path, key, hmac_algorithm, ["PRAGMA integrity_check(1);"])
    found = LOCK_REF_RE.search(checked.stdout.decode(errors="replace"))
    if found is None:
        return
    parent = int(found.group(1))
    cell = None if found.group(3) else int(found.group(2))

    reserve, _, mac_size = PAGE_CIPHER[hmac_algorithm]
    body = PAGE_SIZE - reserve
    mac_at = body + IV_SIZE
    with open(tmp_path, "r+b") as handle:
        handle.seek(0)
        aes_key, hmac_key = derive_keys(key, handle.read(SALT_SIZE))

        if read_page(handle, LOCK_PAGE - 1) != bytes(PAGE_SIZE):
            raise RuntimeError(f"页 {LOCK_PAGE - 1} 并非空页，放弃导出")

        # 密文与 IV 原样复制，AES-CBC 只依赖页内的 IV，页号仅进入摘要
        moved = read_page(handle, LOCK_PAGE)
        write_page(handle, LOCK_PAGE - 1, moved[:mac_at] + page_mac(moved, LOCK_PAGE - 1, hmac_key, hmac_algorithm) + moved[mac_at + mac_size :])

        raw = read_page(handle, parent)
        iv = raw[body:mac_at]
        plain = aes_cbc("-d", aes_key, iv, raw[:body])
        offset = 8 if cell is None else struct.unpack_from(">H", plain, 12 + 2 * cell)[0]
        if struct.unpack_from(">I", plain, offset)[0] != LOCK_PAGE:
            raise RuntimeError(f"页 {parent} 该位置并未指向锁页，放弃导出")
        patched = plain[:offset] + struct.pack(">I", LOCK_PAGE - 1) + plain[offset + 4 :]
        encrypted = aes_cbc("-e", aes_key, iv, patched) + iv
        write_page(handle, parent, encrypted + page_mac(encrypted, parent, hmac_key, hmac_algorithm) + raw[mac_at + mac_size :])


def db_decrypt(db_path: Path, out_path: str, key: str, hmac_algorithm: str) -> None:
    if Path(out_path).resolve() == db_path.resolve():
        raise ValueError(f"输出路径不能与源数据库相同: {out_path}")
    if Path(out_path).is_dir():
        raise ValueError(f"输出路径是目录，拒绝覆盖: {out_path}")
    # 不足一个密文页时 sqlcipher 不报错，会导出一个空库；照常导出，只提示结果为空
    if db_path.stat().st_size < HEADER_SIZE + PAGE_SIZE:
        print(f"[{PROG}] 警告: {db_path.name}: 文件过小，导出结果为空库", file=sys.stderr)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        fd, tmp_path = tempfile.mkstemp(dir="/tmp")
    except OSError:
        fd, tmp_path = tempfile.mkstemp()
    os.close(fd)
    try:
        with db_path.open("rb") as src, open(tmp_path, "wb") as dst:
            src.seek(HEADER_SIZE)
            shutil.copyfileobj(src, dst)

        if db_path.stat().st_size >= HEADER_SIZE + LOCK_PAGE * PAGE_SIZE:
            relocate_lock_page(tmp_path, key, hmac_algorithm)

        Path(out_path).unlink(missing_ok=True)

        out_sql = out_path.replace("'", "''")
        result = run_sqlcipher(tmp_path, key, hmac_algorithm, [
            f"ATTACH DATABASE '{out_sql}' AS plaintext KEY '';",
            "SELECT sqlcipher_export('plaintext');",
            "DETACH DATABASE plaintext;",
        ])
        if result.returncode != 0:
            raise RuntimeError(sqlcipher_reason(result.returncode, result.stderr.decode(errors="replace")))
    finally:
        Path(tmp_path).unlink()


def sqlcipher_reason(code: int, stderr: str) -> str:
    """把 sqlcipher 的多行 stderr 归纳为一行原因；未识别时取末行"""
    # 密钥错误与非加密库都在第 1 页 HMAC 校验处失败，sqlcipher 无法区分两者
    if "hmac check failed" in stderr:
        return "密钥不匹配或文件不是加密库"
    lines = [line for line in stderr.splitlines() if line.strip()]
    return f"sqlcipher 失败 ({code}): {lines[-1].strip() if lines else '无输出'}"


def main() -> None:
    parser = argparse.ArgumentParser(description="解密 QQ NT 数据库文件")
    parser.add_argument("-d", "--db-dir", required=True, help="数据库目录")
    parser.add_argument("-k", "--key", help="数据库密钥")
    parser.add_argument("-g", "--gpro-key", help="gpro 数据库密钥")
    parser.add_argument("files", nargs="*", metavar="file", help="要解密的文件名；省略时解密全部 .db")
    parser.add_argument("-o", "--output-dir", default=".", help="输出目录，默认为 .")
    parser.add_argument("-f", "--name-format", default="{filename}", help="输出文件名模版，斜杠表示目录层，默认为 '{filename}'")
    args = parser.parse_args()

    db_dir = Path(args.db_dir).expanduser().resolve()
    files = args.files or sorted(db.name for db in db_dir.glob("*.db"))

    failed = 0
    for name in files:
        db_path = db_dir / name
        if not db_path.is_file():
            print(f"[{PROG}] 警告: 跳过 {name}: 文件不存在", file=sys.stderr)
            failed += 1
            continue
        cipher = db_cipher(name, args.key, args.gpro_key)
        if cipher is None:
            print(f"[{PROG}] 警告: 跳过 {name}: 缺少可用密钥", file=sys.stderr)
            failed += 1
            continue
        key, hmac_algorithm = cipher
        try:
            out_path = safe_output_path(args.output_dir, args.name_format.format(filename=name))
            db_decrypt(db_path, out_path, key, hmac_algorithm)
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"[{PROG}] 警告: {name}: {exc}", file=sys.stderr)
            failed += 1

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
