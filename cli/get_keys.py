#!/usr/bin/env python3
"""读取 QQ NT 数据库密钥与账号信息。

按 -u/-a 过滤账号标记，格式无效的标记静默跳过；对每个匹配的账号按 KEY_SOURCES 逐类匹配数据库文件并计算密钥。
每条账号记录的 keys 按匹配优先级排列，每项含 name、pattern、key、hmac_algorithm 与 key_note；
数据库目录中没有匹配文件的类别不列出，有匹配文件但无法取得密钥时 key 为 null。
"""

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

PROG = Path(__file__).name


class KeyUnavailable(Exception):
    """密钥获取器无法从匹配的文件取得密钥；消息以文件名开头，后接原因"""


class KeySource(NamedTuple):
    name: str
    # 文件名 glob，可引用账号记录的字段
    pattern: str
    hmac_algorithm: str
    # (账号记录, 匹配的文件) -> (密钥, 写入 key_note 的附加信息)
    read: Callable[[dict[str, str], list[Path]], tuple[str, dict[str, str]]]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def md5(data: str | bytes) -> str:
    return hashlib.md5(data.encode() if isinstance(data, str) else data).hexdigest()


def db_rand(dbs: list[Path]) -> str:
    """返回 QQ_NT DB 标记后的 8 位随机串；无合格匹配时返回空串。"""
    # 明文前导位于第 1 页起始的 1024 字节内，按体积升序取首个携带 QQ_NT DB 标记的库
    for db in sorted(dbs, key=lambda path: path.stat().st_size):
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


def read_nt_key(account: dict[str, str], files: list[Path]) -> tuple[str, dict[str, str]]:
    """缺少 rand 时仍以空串计算密钥"""
    rand = db_rand(files)
    return md5(account["uid_hash"] + rand), {"rand": rand}


def read_gpro_key(account: dict[str, str], files: list[Path]) -> tuple[str, dict[str, str]]:
    db = files[0]
    try:
        salt = gpro_salt(db)
    except OSError as exc:
        raise KeyUnavailable(f"{db.name} 文件头读取失败: {exc}") from exc
    if not salt:
        raise KeyUnavailable(f"{db.name} 文件头无法识别盐值")
    return gpro_key(account["uin"], salt), {"salt": salt.decode("ascii", errors="replace")}


# 顺序即匹配优先级: decrypt_db.py 对每个文件使用首条匹配的规则，专用库须排在通配模式之前
KEY_SOURCES = (
    KeySource("gpro", "gpro_v1-6_{uid}.db", "HMAC_SHA512", read_gpro_key),
    KeySource("nt", "*.db", "HMAC_SHA1", read_nt_key),
)


def scan_accounts(root: Path, user: str | None = None, qq: str | None = None) -> list[dict[str, str]]:
    """按 user 与 qq (uin 或 uid) 过滤账号记录"""
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
        accounts.append({
            "qq_path": str(qq_path),
            "user": qq_path.parent.name,
            "uin": uin,
            "uid": uid,
            "uid_hash": uid_hash,
            "path_hash": path_hash,
            "db_dir": str(db_dir),
        })
    return accounts


def account_keys(account: dict[str, str], *, verbose: bool) -> list[dict[str, object]]:
    who = f"{account['user']}.{account['uin']}"
    keys = []
    for source in KEY_SOURCES:
        pattern = source.pattern.format(**account)
        files = sorted(Path(account["db_dir"]).glob(pattern))
        if not files:
            if verbose:
                log(f"{PROG}: 用户 {who} 无 {source.name} 数据库，未取得 {source.name} 密钥")
            continue
        try:
            key, note = source.read(account, files)
        except KeyUnavailable as exc:
            key, note = None, {}
            if verbose:
                log(f"{PROG}: 用户 {who} 的 {source.name} 数据库 {exc}，未取得 {source.name} 密钥")
        keys.append({"name": source.name, "pattern": pattern, "key": key, "hmac_algorithm": source.hmac_algorithm, "key_note": note})
    return keys


def read_keys(root: Path, user: str | None, qq: str | None, *, verbose: bool = False) -> list[dict[str, object]]:
    return [{**account, "keys": account_keys(account, verbose=verbose)} for account in scan_accounts(root, user, qq)]


def help_text() -> str:
    """返回唯一的帮助文本；stdout 不是终端时移除其中的 ANSI 样式"""
    prog = Path(sys.argv[0]).name
    text = f"""\033[1m读取 QQ NT 数据库密钥与账号信息 -- 输出 JSON 数组\033[0m

\033[1;4m用法:\033[0m
  \033[1m{prog}\033[0m [选项]

\033[1;4m选项:\033[0m
  \033[1m-u, --user <ID>\033[0m                   Android 用户 ID
  \033[1m-a, --qq <uin/uid>\033[0m                QQ uin 或 uid 文本
  \033[1m-r, --root-dir <目录=/>\033[0m           扫描根目录 \033[2m(默认: /)\033[0m
  \033[1m-v, --verbose\033[0m                     显示详细调试信息
  \033[1m-h, --help\033[0m                        显示本帮助

\033[1;4m输出:\033[0m
  每个匹配的账号一条记录，含 user、uin、uid、db_dir 与 keys。
  keys 按匹配优先级列出各类数据库的 name、pattern、key、hmac_algorithm 与 key_note。
  数据库目录中没有对应文件的类别不列出，有对应文件但无法取得密钥时 key 为 null。

\033[1;4m示例:\033[0m
  读取全部账号的密钥
  {prog}

  只读取 Android 用户 0 下指定账号的密钥
  {prog} -u 0 -a <uin>

  从其他根目录读取，其下须有 data/user/<ID>/com.tencent.mobileqq
  {prog} -r <目录>
"""
    return text if sys.stdout.isatty() else re.sub(r"\033\[[0-9;]*m", "", text)


class HelpParser(argparse.ArgumentParser):
    """帮助文本自持，argparse 只负责 -h 的触发与退出"""

    def format_help(self) -> str:
        return help_text()

    def format_usage(self) -> str:
        """参数错误时不输出 argparse 生成的 usage，只保留错误消息"""
        return ""


def main() -> None:
    parser = HelpParser()
    parser.add_argument("-u", "--user")
    parser.add_argument("-a", "--qq")
    parser.add_argument("-r", "--root-dir", default="/")
    parser.add_argument("-v", "--verbose", action="store_true")
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
