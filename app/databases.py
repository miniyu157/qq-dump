"""补全子命令缺省的数据库路径: 选择账号后即时解密到临时目录。"""

import argparse
import atexit
import sys
import tempfile
from pathlib import Path

from app.ansi import err
from app.errors import AppError
from app.scripts import decrypt, get_keys, qq_data_accessible, require_qq_data, scan_accounts
from app.utils import require_binaries, warn_log
from lib.tui.choose import choose

__all__ = ["complete_databases"]


def complete_databases(args: argparse.Namespace, databases: list[tuple[str, str]]) -> None:
    """按 (args 属性名, 数据库文件名) 补全缺省路径；显式路径原样保留，不检查存在性。"""
    missing = [(attr, name) for attr, name in databases if getattr(args, attr) is None]
    if not missing:
        return
    names = [name for _, name in missing]

    # 临时数据库优先放在 tmpfs，创建失败时退回系统临时目录
    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-", dir="/tmp")
    except OSError:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-")
    atexit.register(temp_dir.cleanup)

    missing_text = ", ".join(f"{err.HL}{name}{err.RESET}" for name in names)
    print(f"需要数据库: {missing_text}\n将解密到临时目录以使用: {err.HL}{temp_dir.name}{err.RESET}\n运行 {err.HL}help{err.RESET} 命令以了解如何手动选择", file=sys.stderr)

    require_qq_data(args.root_dir, args.user)
    require_binaries("数据库解密", ["sqlcipher"])
    as_root = not qq_data_accessible(args.root_dir, args.user)

    account = _select_account(args, as_root=as_root)
    record = _account_key(account, args.root_dir, as_root=as_root)

    if not decrypt(record, temp_dir.name, "{filename}", names, as_root=as_root):
        raise AppError(f"解密失败: {', '.join(names)}")
    for attr, name in missing:
        out_path = Path(temp_dir.name) / name
        if not out_path.is_file():
            raise AppError(f"解密失败: {name}")
        setattr(args, attr, str(out_path))


def _select_account(args: argparse.Namespace, *, as_root: bool) -> dict[str, object]:
    """扫描账号，按 -u/-a 过滤后读取用户选择。"""
    accounts = [
        account
        for account in scan_accounts(args.root_dir, as_root=as_root)
        if (not args.user or account["user"] == args.user)
        and (not args.qq or args.qq in (account["uin"], account["uid"]))
    ]
    if not accounts:
        warn_log("未找到可选的账号")
        sys.exit(1)

    options = [f"{account['user']}.{account['uin']}" for account in accounts]
    title = f"\n{err.INFO}请选择账号:{err.RESET}"
    try:
        choice = choose(options, title=title)
    except (EOFError, ValueError):
        sys.exit("未选择账号")
    return accounts[choice]


def _account_key(account: dict[str, object], root_dir: str | None, *, as_root: bool) -> dict[str, object]:
    """取所选账号的密钥记录。"""
    for record in get_keys(account["user"], account["uid"], root_dir, as_root=as_root):
        if record.get("user") == account["user"] and record.get("uid") == account["uid"]:
            return record
    raise AppError(f"未找到账号密钥: {account['user']}.{account['uin']}")
