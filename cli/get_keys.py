#!/usr/bin/env python3
"""读取 QQ NT 数据库密钥与账号信息。"""

import argparse
import hashlib
import json
import re
import sys
from itertools import pairwise
from pathlib import Path


def md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


def db_rand(db_dir: Path) -> str:
    """返回 QQ_NT DB 标记后的 8 位随机串；无合格匹配时返回空串。"""
    # 明文前导位于第 1 页起始的 1024 字节内，按体积升序取首个携带 QQ_NT DB 标记的库
    for db in sorted(db_dir.glob("*.db"), key=lambda path: path.stat().st_size):
        with db.open("rb") as f:
            lines = re.findall(rb"[\x20-\x7e]+", f.read(1024))
        for line, rand in pairwise(lines):
            if b"QQ_NT DB" in line:
                rand = rand.decode("ascii")
                if re.fullmatch(r"[A-Za-z0-9]{8}", rand):
                    return rand
                break
    return ""


def gpro_salt(db_path: Path) -> bytes:
    """读取 gpro 文件头中 Guild DB 标记后的盐值；头部结构不符时返回空字节串。"""
    # 1024 字节明文头部：标记之后依次为 4 字节小端长度与对应长度的盐值
    with db_path.open("rb") as f:
        header = f.read(1024)
    marker = b"Guild DB v1.0.0"
    start = header.find(marker)
    if start < 0:
        return b""
    length_at = start + len(marker)
    length = int.from_bytes(header[length_at:length_at + 4], "little")
    salt = header[length_at + 4:length_at + 4 + length]
    return salt if length == 16 and len(salt) == 16 else b""


def gpro_key(uin: str, salt: bytes) -> str:
    uin_bytes = uin.encode()
    md5_sha1 = md5(hashlib.sha1(uin_bytes).digest())
    user_seed = md5(md5(uin_bytes) + md5_sha1)
    return md5(md5(salt) + user_seed)


def read_keys(root: Path, user: str | None, qq: str | None) -> list[dict[str, object]]:
    records = []
    pattern = f"data/user/{user or '*'}/com.tencent.mobileqq/files/uid/*"
    for uid_path in sorted(root.glob(pattern)):
        qq_path = uid_path.parent.parent.parent
        uin, _, uid = uid_path.name.partition("###")
        if qq and qq not in (uin, uid):
            continue

        uid_hash = md5(uid)
        path_hash = md5(uid_hash + "nt_kernel")
        db_dir = qq_path / "databases" / "nt_db" / f"nt_qq_{path_hash}"
        rand = db_rand(db_dir)
        record = {
            "qq_path": str(qq_path),
            "user": qq_path.parent.name,
            "uin": uin,
            "uid": uid,
            "uid_hash": uid_hash,
            "path_hash": path_hash,
            "db_dir": str(db_dir),
            "rand": rand,
            "key": md5(uid_hash + rand),
            "gpro_file": None,
            "gpro_salt": None,
            "gpro_key": None,
        }

        gpro_name = f"gpro_v1-6_{uid}.db"
        gpro_path = db_dir / gpro_name
        if gpro_path.is_file():
            record["gpro_file"] = gpro_name
            try:
                salt = gpro_salt(gpro_path)
            except OSError as exc:
                print(f"警告: gpro 文件头读取失败，跳过: {gpro_path}: {exc}", file=sys.stderr)
            else:
                if salt:
                    record["gpro_salt"] = salt.decode("ascii", errors="replace")
                    record["gpro_key"] = gpro_key(uin, salt)
                else:
                    print(f"警告: gpro 文件头无法识别盐值，跳过: {gpro_path}", file=sys.stderr)

        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="读取 QQ NT 数据库密钥与账号信息")
    parser.add_argument("-u", "--user", help="选择 Android 用户 ID")
    parser.add_argument("-a", "--qq", help="选择 QQ 账号，QQ uin 或 uid")
    parser.add_argument("-r", "--root-dir", default="/", help="根目录，默认为 /")
    args = parser.parse_args()

    root = Path(args.root_dir).expanduser().resolve()
    print(json.dumps(read_keys(root, args.user, args.qq), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(f"错误: {exc}")
