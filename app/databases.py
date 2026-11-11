"""补全子命令缺省的数据库路径: 选择账号后即时解密到临时目录。"""

import argparse
import atexit
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.accounts import prepare_access
from app.ansi import err
from app.scripts import decrypt, get_keys
from app.utils import cancel_log, warn_log
from lib.tui.choose import ChoiceCancelled, choose

__all__ = ["complete_database_dir", "complete_databases", "print_database_hint"]

_DATABASE_HINTS = {
    "profile_db": ("--profile-db", "QQDUMP_PROFILE_DB"),
    "nt_msg_db": ("--nt-msg-db", "QQDUMP_NT_MSG_DB"),
}


def print_database_hint(args: argparse.Namespace, databases: Sequence[tuple[str, str]], *, purpose: str = "") -> None:
    """向 stderr 说明缺失的数据库及对应 CLI、环境变量入口，不执行补全。"""
    missing = [(attr, name) for attr, name in databases if getattr(args, attr) is None]
    if not missing:
        return
    names = ", ".join(f"{err.HL}{name}{err.RESET}" for _, name in missing)
    flags = "、".join(f"{err.HL}{_DATABASE_HINTS[attr][0]}{err.RESET}" for attr, _ in missing)
    envs = "、".join(f"{err.HL}{_DATABASE_HINTS[attr][1]}{err.RESET}" for attr, _ in missing)
    print(f"{purpose}需要数据库: {names}\n也可以使用 {flags}、环境变量或 .env 中的 {envs} 预先设置\n", file=sys.stderr)


def complete_databases(args: argparse.Namespace, databases: list[tuple[str, str]]) -> None:
    """按 (args 属性名, 数据库文件名) 补全值为 None 的文件参数；显式路径原样保留，不检查存在性。

    从 args.user、qq、root_dir 选择账号，只解密缺失参数对应的库，成功后填回文件路径。
    输出账号选择和解密提示，临时目录在进程退出时清理。
    依赖缺失、取消或解密失败时退出进程。
    """
    missing = [(attr, name) for attr, name in databases if getattr(args, attr) is None]
    if not missing:
        return
    names = [name for _, name in missing]
    directory = _decrypt_to_temp(args, names)
    for attr, name in missing:
        setattr(args, attr, str(directory / name))


def complete_database_dir(args: argparse.Namespace, *, attr: str, databases: Sequence[str]) -> None:
    """补全 args 中为 None 的目录参数；显式目录原样保留，不检查或写入该目录。

    databases 指定需解密的库文件名；从 args.user、qq、root_dir 选择账号，输出账号选择和解密提示，
    将全部指定库解密到同一临时目录后才填回 attr，临时目录在进程退出时清理。
    依赖缺失、取消或解密失败时退出进程。
    """
    if getattr(args, attr) is not None:
        return
    directory = _decrypt_to_temp(args, list(databases))
    setattr(args, attr, str(directory))


def _decrypt_to_temp(args: argparse.Namespace, names: list[str]) -> Path:
    as_root = prepare_access(args.root_dir, args.user, decrypting=True)

    # POSIX 下临时数据库优先放在 tmpfs，创建失败时退回系统临时目录；Windows 的 /tmp 会落到当前盘根目录，直接用系统临时目录
    # 取消选择经 sys.exit 退出时由 atexit 清理
    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-", dir=None if sys.platform == "win32" else "/tmp")
    except OSError:
        temp_dir = tempfile.TemporaryDirectory(prefix="qq-dump-")
    atexit.register(temp_dir.cleanup)
    print(f"将解密到临时目录以使用: {err.HL}{temp_dir.name}{err.RESET}\n", file=sys.stderr)

    record = _select_account(args, as_root=as_root)

    if not decrypt(record, temp_dir.name, "{filename}", names, copy_plain=True, as_root=as_root):
        warn_log(f"解密失败: {', '.join(names)}")
        sys.exit(1)
    directory = Path(temp_dir.name)
    for name in names:
        if not (directory / name).is_file():
            warn_log(f"解密失败: {name}")
            sys.exit(1)
    return directory


def _select_account(args: argparse.Namespace, *, as_root: bool) -> dict[str, object]:
    """从匹配账号中读取用户选择，返回所选账号的密钥记录，不验证解密有效性。"""
    records = get_keys(args.user, args.qq, args.root_dir, as_root=as_root)
    if not records:
        warn_log("未找到可用的账号")
        sys.exit(1)

    options = [f"{record['user']}.{record['uin']}" for record in records]
    title = f"{err.BOLD}{err.INFO}请选择账号:{err.RESET}"
    try:
        choice = choose(options, title=title)
    except (ChoiceCancelled, EOFError):
        cancel_log("未选择账号")
        sys.exit(1)
    except ValueError as exc:
        warn_log(str(exc))
        sys.exit(1)
    return records[choice]
