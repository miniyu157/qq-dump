#!/usr/bin/env python3
"""扫描 QQ NT 账号: 解析账号标记并判断数据库目录能否取得 rand。

作为模块供 get_keys.py 导入，返回含 db_dir 与 rand 的完整记录；
作为程序运行时只输出 user、uid、uin。格式无效的账号标记静默跳过，取不到 rand 的账号警告后跳过。
"""

import argparse
import hashlib
import json
import re
import sys
from itertools import pairwise
from pathlib import Path

__all__ = ["scan_accounts"]

# stderr 消息的来源前缀；stdout 的 JSON 由调用方解析，不加前缀
PROG = Path(__file__).name


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


def missing_rand_reason(db_dir: Path) -> str:
    """db_rand 返回空串时的具体原因"""
    if not db_dir.is_dir():
        return "数据库目录不存在"
    if not any(db_dir.glob("*.db")):
        return "数据库目录中没有 .db 文件"
    return "数据库文件均缺少 QQ_NT DB 标记"


def scan_accounts(root: Path, user: str | None = None, qq: str | None = None) -> list[dict[str, str]]:
    """按 user 与 qq (uin 或 uid) 过滤，返回能取得 rand 的账号记录"""
    accounts = []
    pattern = f"data/user/{user or '*'}/com.tencent.mobileqq/files/uid/*"
    for uid_path in sorted(root.glob(pattern)):
        uin, sep, uid = uid_path.name.partition("###")
        if not (sep and uin and uid):
            continue
        if qq and qq not in (uin, uid):
            continue

        qq_path = uid_path.parents[2]
        uid_hash = md5(uid)
        path_hash = md5(uid_hash + "nt_kernel")
        db_dir = qq_path / "databases" / "nt_db" / f"nt_qq_{path_hash}"
        rand = db_rand(db_dir)
        # 没有 rand 时仍能算出一个形似正常的密钥，但无法解密，不输出该账号
        if not rand:
            print(f"[{PROG}] 警告: 跳过账号 {qq_path.parent.name}.{uin}: {missing_rand_reason(db_dir)}: {db_dir}", file=sys.stderr)
            continue
        accounts.append({
            "qq_path": str(qq_path),
            "user": qq_path.parent.name,
            "uin": uin,
            "uid": uid,
            "uid_hash": uid_hash,
            "path_hash": path_hash,
            "db_dir": str(db_dir),
            "rand": rand,
        })
    return accounts


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描 QQ NT 账号")
    parser.add_argument("-u", "--user", help="选择 Android 用户 ID")
    parser.add_argument("-a", "--qq", help="选择 QQ 账号，QQ uin 或 uid")
    parser.add_argument("-r", "--root-dir", default="/", help="根目录，默认为 /")
    args = parser.parse_args()

    root = Path(args.root_dir).expanduser().resolve()
    accounts = [{"user": a["user"], "uid": a["uid"], "uin": a["uin"]} for a in scan_accounts(root, args.user, args.qq)]
    print(json.dumps(accounts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(f"[{PROG}] 错误: {exc}")
