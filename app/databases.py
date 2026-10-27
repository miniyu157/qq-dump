"""补全子命令缺省的数据库路径: 选择账号后即时解密到临时目录。"""

import argparse
import atexit
import sys
import tempfile
from pathlib import Path

from app.accounts import prepare_access
from app.ansi import err
from app.errors import AppError
from app.scripts import decrypt, get_keys, scan_accounts
from app.utils import warn_log
from lib.tui.choose import choose

__all__ = ["complete_databases"]

# args 属性名 -> (命令行选项, 环境变量)，与 main.py 的解析器和取值规则对应
_PRESETS = {
    "profile_db": ("--profile-db", "QQDUMP_PROFILE_DB"),
    "nt_msg_db": ("--nt-msg-db", "QQDUMP_NT_MSG_DB"),
}


def complete_databases(args: argparse.Namespace, databases: list[tuple[str, str]], purpose: str = "") -> None:
    """按 (args 属性名, 数据库文件名) 补全缺省路径；显式路径原样保留，不检查存在性。

    purpose 为需要这些数据库的功能，拼在提示开头，如 "WebUI 功能" 显示为「WebUI 功能需要数据库: ...」。
    """
    missing = [(attr, name) for attr, name in databases if getattr(args, attr) is None]
    if not missing:
        return
    names = [name for _, name in missing]

    # 先说明为何进入补全，再执行校验；校验失败时用户仍能看到原因
    missing_text = ", ".join(f"{err.HL}{name}{err.RESET}" for name in names)
    flags = "、".join(f"{err.HL}{_PRESETS[attr][0]}{err.RESET}" for attr, _ in missing)
    envs = "、".join(f"{err.HL}{_PRESETS[attr][1]}{err.RESET}" for attr, _ in missing)
    print(f"{purpose}需要数据库: {missing_text}\n也可以使用 {flags}、环境变量或 .env 中的 {envs} 预先设置\n", file=sys.stderr)

    as_root = prepare_access(args.root_dir, args.user, decrypting=True)
    account = _select_account(args, as_root=as_root)
    record = _account_key(account, args.root_dir, as_root=as_root)

    # 临时数据库优先放在 tmpfs，创建失败时退回系统临时目录
    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-", dir="/tmp")
    except OSError:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-")
    atexit.register(temp_dir.cleanup)

    if not decrypt(record, temp_dir.name, "{filename}", names, as_root=as_root):
        raise AppError(f"解密失败: {', '.join(names)}")
    for attr, name in missing:
        out_path = Path(temp_dir.name) / name
        if not out_path.is_file():
            raise AppError(f"解密失败: {name}")
        setattr(args, attr, str(out_path))


def _select_account(args: argparse.Namespace, *, as_root: bool) -> dict[str, object]:
    """扫描可用账号并读取用户选择。"""
    accounts = scan_accounts(args.user, args.qq, args.root_dir, as_root=as_root)
    if not accounts:
        warn_log("未找到可用的账号")
        sys.exit(1)

    options = [f"{account['user']}.{account['uin']}" for account in accounts]
    title = f"{err.INFO}请选择账号:{err.RESET}"
    try:
        choice = choose(options, title=title)
    except (EOFError, ValueError):
        sys.exit("未选择账号")
    return accounts[choice]


def _account_key(account: dict[str, object], root_dir: str | None, *, as_root: bool) -> dict[str, object]:
    """取所选账号的密钥记录；密钥无法计算时 get_keys.py 已给出原因，此处只报告缺失。"""
    for record in get_keys(account["user"], account["uid"], root_dir, as_root=as_root):
        if record.get("user") == account["user"] and record.get("uid") == account["uid"]:
            return record
    raise AppError(f"未找到账号密钥: {account['user']}.{account['uin']}")
