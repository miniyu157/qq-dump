#!/usr/bin/env python3
"""读取 QQ NT 数据库密钥与账号信息。

账号的扫描与过滤由同目录的 scan_accounts 完成，本脚本只在其结果上计算密钥与 gpro 密钥。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from scan_accounts import scan_accounts

PROG = Path(__file__).name


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


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


def read_keys(root: Path, user: str | None, qq: str | None, *, verbose: bool = False) -> list[dict[str, object]]:
    records = []
    for account in scan_accounts(root, user, qq):
        record = {
            **account,
            "key": md5(account["uid_hash"] + account["rand"]),
            "gpro_file": None,
            "gpro_salt": None,
            "gpro_key": None,
        }

        gpro_name = f"gpro_v1-6_{account['uid']}.db"
        gpro_path = Path(account["db_dir"]) / gpro_name
        if gpro_path.is_file():
            record["gpro_file"] = gpro_name
            try:
                salt = gpro_salt(gpro_path)
            except OSError as exc:
                if verbose:
                    log(f"{PROG}: 用户 {account['user']}.{account['uin']} 的 gpro 数据库 {gpro_name} 文件头读取失败: {exc}")
            else:
                if salt:
                    record["gpro_salt"] = salt.decode("ascii", errors="replace")
                    record["gpro_key"] = gpro_key(account["uin"], salt)
                elif verbose:
                    log(f"{PROG}: 用户 {account['user']}.{account['uin']} 的 gpro 数据库 {gpro_name} 文件头无法识别盐值，未取得 gpro 密钥")
        elif verbose:
            log(f"{PROG}: 用户 {account['user']}.{account['uin']} 无 gpro 数据库，未取得 gpro 密钥")
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="读取 QQ NT 数据库密钥与账号信息")
    parser.add_argument("-u", "--user", help="选择 Android 用户 ID")
    parser.add_argument("-a", "--qq", help="选择 QQ 账号，QQ uin 或 uid")
    parser.add_argument("-r", "--root-dir", default="/", help="根目录，默认为 /")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细调试信息")
    args = parser.parse_args()

    root = Path(args.root_dir).expanduser().resolve()
    print(json.dumps(read_keys(root, args.user, args.qq, verbose=args.verbose), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(f"{PROG}: {exc}")
