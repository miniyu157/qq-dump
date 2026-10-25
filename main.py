#!/usr/bin/env python3
import argparse
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

from lib.ansi import _bold, _faint, _good, _hl, _info, _reset, _tty, _warn
from lib.utils import check_binary_deps, check_python_deps, info_log, warn_log
from render.data import render_json
from render.tui import choose

VERSION = "0.1.1"

SCRIPT_DIR = Path(__file__).resolve().parent
CLI_DIR = SCRIPT_DIR / "cli"

DEPENDENCIES = (
    ("python", True, "你需要使用 Python 运行这个项目"),
    ("sudo", False, "自提权时需要"),
    ("sqlcipher", False, "解密数据库时需要"),
    ("chafa", False, "运行 avatar --chafa 时需要"),
)


class AppError(Exception):
    """可预期的用户侧错误，由入口统一输出。"""


def run_script(command: list[str], *, as_root: bool, label: str | None = None, capture_stdout: bool = False) -> subprocess.CompletedProcess[str]:
    """运行命令行；as_root 为真时检查 sudo 依赖并通过 sudo 执行。"""
    if as_root:
        check_binary_deps("提升权限需要以下二进制依赖: ", ["sudo"], log=warn_log)
    if label is not None:
        print(label, file=sys.stderr)
    stdout = subprocess.PIPE if capture_stdout else None
    argv = ["sudo", *command] if as_root else command
    return subprocess.run(argv, stdout=stdout, text=True, check=False)


def run_script_json(command: list[str], label: str, *, as_root: bool) -> list[dict[str, object]]:
    """运行脚本并解析 stdout 的 JSON 数组；command 为 [解释器, 脚本, ...]。"""
    result = run_script(command, as_root=as_root, label=label, capture_stdout=True)
    if result.returncode != 0:
        raise AppError(f"{Path(command[1]).name} 失败 ({result.returncode})")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AppError(f"{Path(command[1]).name} 输出无效: {exc}") from exc


def get_keys_argv(user: str | None, qq: str | None, root_dir: str | None) -> list[str]:
    """构造 get_keys.py 命令行，只追加已指定的过滤条件。"""
    command = [sys.executable, str(CLI_DIR / "get_keys.py")]
    if user is not None:
        command += ["-u", user]
    if qq is not None:
        command += ["-a", qq]
    if root_dir is not None:
        command += ["-r", root_dir]
    return command


def decrypt_db_argv(record: dict[str, object], output_dir: str, name_format: str, files: list[str]) -> list[str]:
    """构造 decrypt_db.py 命令行；record 缺少 gpro 密钥时不传 -g。"""
    command = [
        sys.executable, str(CLI_DIR / "decrypt_db.py"),
        "-d", record["db_dir"],
        "-k", record["key"],
    ]
    if record["gpro_key"]:
        command += ["-g", record["gpro_key"]]
    return command + ["-o", output_dir, "-f", name_format, *files]


def decrypt_label(record: dict[str, object], files: str) -> str:
    """返回账号解密提示，files 为文件描述文本。"""
    return f"正在解密账号 {record['user']} - {record['uin']} 的 {files}"


def _qq_data_error(target: Path) -> NoReturn:
    """输出 QQ 数据目录缺失的错误与根目录提示，并退出。"""
    print(file=sys.stderr)
    warn_log(f"QQ 数据目录不存在: {target}")
    info_log(f"TIP: 或许可以使用 {_hl}--root-dir{_reset} 手动设置根目录")
    sys.exit(1)


def require_qq_data(args: argparse.Namespace) -> None:
    """QQ 应用数据目录确定不存在时中止；无法读取时不拦截。"""
    users = Path(args.root_dir or "/").expanduser() / "data" / "user"
    target = users / (args.user or "*") / "com.tencent.mobileqq"

    if args.user is not None:
        candidates = [target]
    else:
        try:
            candidates = [path / "com.tencent.mobileqq" for path in users.iterdir()]
        except (FileNotFoundError, NotADirectoryError):
            candidates = []
        except OSError:
            return

    unknown = False
    for candidate in candidates:
        try:
            candidate.stat()
            return
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            unknown = True
    if not unknown:
        _qq_data_error(target)


def _can_read(qq_dir: Path) -> bool:
    """判断 QQ 目录下的账号目录是否可读。"""
    try:
        with os.scandir(qq_dir / "files" / "uid"):
            return True
    except FileNotFoundError:
        return os.access(qq_dir, os.R_OK | os.X_OK)
    except OSError:
        return False


def qq_data_accessible(args: argparse.Namespace) -> bool:
    """当前身份能否直接读取 QQ 数据目录。"""
    if os.geteuid() == 0:
        return True

    users = Path(args.root_dir or "/").expanduser() / "data" / "user"
    if args.user is not None:
        qq_dirs = [users / args.user / "com.tencent.mobileqq"]
    else:
        try:
            qq_dirs = [path / "com.tencent.mobileqq" for path in users.iterdir()]
        except OSError:
            return False

    return bool(qq_dirs) and all(_can_read(path) for path in qq_dirs)


def cmd_key(args: argparse.Namespace) -> None:
    """调用 get_keys.py 输出密钥记录。"""
    require_qq_data(args)
    as_root = not qq_data_accessible(args)
    command = get_keys_argv(args.user, args.qq, args.root_dir)
    raise SystemExit(run_script(command, as_root=as_root).returncode)


def cmd_db(args: argparse.Namespace) -> None:
    """获取密钥，再逐账号调用 decrypt_db.py 解密。"""
    check_binary_deps("数据库解密需要以下二进制依赖: ", ["sqlcipher"], log=warn_log)
    require_qq_data(args)
    as_root = not qq_data_accessible(args)
    get_keys = get_keys_argv(args.user, args.qq, args.root_dir)
    records = run_script_json(get_keys, "正在获取密钥...", as_root=as_root)

    files_label = f"{_hl}{' '.join(args.files) or '全部数据库文件'}{_reset}"
    failed = False
    for record in records:
        # 账号字段在此展开；{filename} 留给 decrypt_db.py 按实际文件名填充
        name_format = args.name_format.format(**record, filename="{filename}")
        command = decrypt_db_argv(record, args.output_dir, name_format, args.files)
        if run_script(command, as_root=as_root, label=decrypt_label(record, files_label)).returncode != 0:
            failed = True

    if failed:
        sys.exit(1)


def cmd_avatar(args: argparse.Namespace) -> None:
    """获取并渲染指定 UIN 的头像；--chafa 交给 chafa，--ascii 使用真彩色字符画。"""
    from render.image import render
    from service.avatars import avatar

    if args.chafa:
        check_binary_deps("使用 chafa 查看头像需要以下二进制依赖: ", ["chafa"], log=warn_log)

    result = avatar(args.uin)
    if result is None:
        raise AppError(f"无法获取头像: {args.uin}")
    data, _ = result
    if args.chafa:
        proc = subprocess.run(["chafa", "-"], input=data, check=False)
        raise SystemExit(proc.returncode)
    render(data, use_ascii=args.ascii)


def cmd_web(args: argparse.Namespace) -> None:
    """启动本地 WebUI。"""
    complete_databases(args, [("profile_db", "profile_info.db")])

    from web.server import serve

    serve(args.profile_db, args.nt_msg_db)


def cmd_friends(args: argparse.Namespace) -> None:
    """输出好友 JSON。"""
    complete_databases(args, [("profile_db", "profile_info.db")])

    from api import load_friends

    render_json(friend._asdict() for friend in load_friends(args.profile_db))


def cmd_owner(args: argparse.Namespace) -> None:
    """输出主人信息。"""
    complete_databases(args, [("profile_db", "profile_info.db")])

    from api import load_owner

    owner = load_owner(args.profile_db)
    render_json(owner._asdict() if owner is not None else None)


def select_account(args: argparse.Namespace, *, as_root: bool) -> dict[str, object]:
    """扫描账号并读取用户选择。"""
    scan = [sys.executable, str(CLI_DIR / "scan_accounts.py")]
    if args.root_dir is not None:
        scan += ["-r", args.root_dir]
    accounts = [
        account
        for account in run_script_json(scan, "正在扫描账号...", as_root=as_root)
        if (not args.user or account["user"] == args.user)
        and (not args.qq or args.qq in (account["uin"], account["uid"]))
    ]
    if not accounts:
        print(f"{_info}未找到可选的账号{_reset}", file=sys.stderr)
        sys.exit(1)

    options = [f"{account['user']}.{account['uin']}" for account in accounts]
    title = f"\n{_info}请选择账号:{_reset}"
    try:
        choice = choose(options, title=title)
    except (EOFError, ValueError):
        sys.exit("未选择账号")
    return accounts[choice]


def account_key_record(account: dict[str, object], args: argparse.Namespace, *, as_root: bool) -> dict[str, object]:
    """调用 get_keys.py 取所选账号的密钥记录。"""
    command = get_keys_argv(account["user"], account["uid"], args.root_dir)
    for record in run_script_json(command, "正在获取密钥...", as_root=as_root):
        if record.get("user") == account["user"] and record.get("uid") == account["uid"]:
            return record
    raise AppError(f"未找到账号密钥: {account['user']}.{account['uin']}")


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

    missing_text = ", ".join(f"{_hl}{name}{_reset}" for name in names)
    print(f"需要数据库: {missing_text}\n将解密到临时目录以使用: {_hl}{temp_dir.name}{_reset}\n运行 {_hl}help{_reset} 命令以了解如何手动选择", file=sys.stderr)

    require_qq_data(args)
    check_binary_deps("数据库解密需要以下二进制依赖: ", ["sqlcipher"], log=warn_log)
    as_root = not qq_data_accessible(args)

    account = select_account(args, as_root=as_root)
    record = account_key_record(account, args, as_root=as_root)

    command = decrypt_db_argv(record, temp_dir.name, "{filename}", names)
    files_label = f"{_hl}{' '.join(names)}{_reset}"
    if run_script(command, as_root=as_root, label=decrypt_label(record, files_label)).returncode != 0:
        raise AppError(f"解密失败: {', '.join(names)}")
    for attr, name in missing:
        out_path = Path(temp_dir.name) / name
        if not out_path.is_file():
            raise AppError(f"解密失败: {name}")
        setattr(args, attr, str(out_path))


def cmd_legacy(args: argparse.Namespace) -> None:
    """检查依赖、补全缺失数据库后启动 legacy。"""
    check_python_deps("legacy 功能需要使用以下 Python 依赖: ", ["blackboxprotobuf"], log=warn_log)
    complete_databases(args, [("profile_db", "profile_info.db"), ("nt_msg_db", "nt_msg.db")])

    legacy_main = SCRIPT_DIR / "legacy-dump-chat" / "main.py"
    proc = subprocess.run([sys.executable, str(legacy_main), "-p", args.profile_db, "-n", args.nt_msg_db, "-o", args.output_dir], check=False)
    raise SystemExit(proc.returncode)


def cmd_check(args: argparse.Namespace) -> None:
    """检查运行时依赖，按必选与可选列出结果。"""
    print(f"{_bold}QQ DUMP 依赖检查{_reset}", file=sys.stderr)
    print(file=sys.stderr)
    results = [
        (name, required, purpose, shutil.which(name) is not None)
        for name, required, purpose in DEPENDENCIES
    ]
    for index, (required, label) in enumerate(((True, "必选"), (False, "可选"))):
        if index:
            print(file=sys.stderr)
        print(f"{_bold}{label}依赖{_reset}", file=sys.stderr)
        for name, is_required, purpose, found in results:
            if is_required != required:
                continue
            status = "已找到" if found else "未找到"
            color = _good if found else _warn
            print(f"{_good}●{_reset} {color}{status}{_reset}: {name} {_faint}({purpose}){_reset}", file=sys.stderr)
    missing = sum(not found for _, _, _, found in results)
    print(f"\n共计: {len(results)} 项, 缺失: {missing} 项", file=sys.stderr)
    if any(required and not found for _, required, _, found in results):
        sys.exit(1)


def cmd_help(args: argparse.Namespace) -> None:
    sys.stdout.write(help_text())


def cmd_menu(args: argparse.Namespace) -> None:
    """无子命令时显示主菜单。"""
    title = (
        f"{_bold}QQ DUMP TUI v{VERSION}{_reset}\n"
        f"{_hl}https://github.com/miniyu157/qq-dump{_reset}\n\n"
        f"{_info}今天想要做些什么?{_reset}"
    )
    menu = (
        (f"运行 WebUI 服务器 {_faint}(需要数据库文件){_reset}", cmd_web),
        (f"运行 Legacy 消息导出 {_faint}(需要数据库文件){_reset}", cmd_legacy),
        ("查看 CLI 帮助", cmd_help),
        ("运行依赖检查", cmd_check),
    )
    try:
        choice = choose([label for label, _ in menu], title=title)
    except (EOFError, ValueError):
        sys.exit("未选择操作")
    menu[choice][1](args)


def help_text() -> str:
    """返回唯一的帮助文本；-h、help 子命令与 argparse 共用。"""
    prog = Path(sys.argv[0]).name
    _title = "\033[1;4m" if _tty else ""
    _cmd_a = f"{_bold}{_hl}" if _tty else ""
    return f"""{_bold}QQ DUMP v{VERSION} -- 从 NTQQ 数据库得到信息{_reset}

  {_faint}tip: 数据库文件参数 (如 -p/-n) 被需要且未指定时，
  会显示账号选择界面，并即时解密补齐。
  未指定子命令时显示菜单。{_reset}

{_title}用法:{_reset}
  {_bold}{prog}{_reset} [选项] [<子命令>] [命令选项] [参数]

{_title}选项 (全局):{_reset}
  {_bold}-u, --user <ID>{_reset}                  Android 用户 ID{_reset}
  {_bold}-a, --qq <uin/uid>{_reset}               QQ uin 或 uid 文本{_reset}
  {_bold}-r, --root-dir <目录=/>{_reset}          扫描根目录 {_faint}(默认: /){_reset}
  {_bold}-p, --profile-db <路径>{_reset}          profile_info.db 路径{_reset}
  {_bold}-n, --nt-msg-db <路径>{_reset}           nt_msg.db 路径{_reset}
  {_bold}-o, --output-dir <目录=.>{_reset}        输出目录 {_faint}(默认: 当前目录){_reset}

{_title}子命令:{_reset}
  {_cmd_a}key{_reset} [-u] [-a] [-r]               为选定用户计算数据库密钥

  {_cmd_a}db{_reset} [-u] [-a] [-r] [-o] [-f] [files...] 为选定用户解密数据库文件
    {_bold}-f, --name-format <模版>{_reset}       输出文件名模版，斜杠表示目录层
                                   {_faint}(默认: {{user}}.{{uin}}/{{filename}}){_reset}

  {_cmd_a}check{_reset}                            检查运行时依赖

  {_cmd_a}web{_reset} [-p]                         启动本地 WebUI

  {_cmd_a}friends{_reset} [-p]                     输出好友 JSON

  {_cmd_a}owner{_reset} [-p]                       输出主人信息

  {_cmd_a}l, legacy{_reset} [-p] [-n] [-o]         启动 legacy-dump-chat

  {_cmd_a}avatar{_reset} <uin> [--chafa|--ascii]   根据官方 API 获取头像并渲染
    {_bold}--chafa{_reset}                        改用 chafa 查看头像
    {_bold}--ascii{_reset}                        改用真彩色 ASCII 字符画

{_title}选项 (程序):{_reset}
  {_bold}-h, --help{_reset}                       显示本帮助{_reset}
  {_bold}-v, --version{_reset}                    显示版本号
"""


class HelpParser(argparse.ArgumentParser):
    """帮助文本自持，argparse 只负责 -h 的触发与退出"""

    def format_help(self) -> str:
        """始终返回同一份帮助，忽略子解析器的 prog。"""
        return help_text()


def main() -> None:
    """程序入口：装配解析器并分发到对应子命令。"""
    common = argparse.ArgumentParser(add_help=False)
    # 公共选项可位于子命令前后；SUPPRESS 防止子解析器默认值覆盖此前已解析的取值
    common.add_argument("-u", "--user", default=argparse.SUPPRESS)
    common.add_argument("-a", "--qq", default=argparse.SUPPRESS)
    common.add_argument("-r", "--root-dir", dest="root_dir", default=argparse.SUPPRESS)
    common.add_argument("-p", "--profile-db", dest="profile_db", default=argparse.SUPPRESS)
    common.add_argument("-n", "--nt-msg-db", dest="nt_msg_db", default=argparse.SUPPRESS)
    common.add_argument("-o", "--output-dir", dest="output_dir", default=argparse.SUPPRESS)
    common.add_argument("-v", "--version", action="version", version=f"v{VERSION}")

    parser = HelpParser(parents=[common])
    # 未指定子命令时显示菜单
    parser.set_defaults(func=cmd_menu)
    sub = parser.add_subparsers(dest="command", parser_class=HelpParser)
    sub.add_parser("key", parents=[common]).set_defaults(func=cmd_key)
    db_parser = sub.add_parser("db", parents=[common])
    db_parser.add_argument("files", nargs="*")
    db_parser.add_argument("-f", "--name-format", default="{user}.{uin}/{filename}")
    db_parser.set_defaults(func=cmd_db)

    sub.add_parser("check", parents=[common]).set_defaults(func=cmd_check)
    sub.add_parser("web", parents=[common]).set_defaults(func=cmd_web)
    sub.add_parser("friends", parents=[common]).set_defaults(func=cmd_friends)
    sub.add_parser("owner", parents=[common]).set_defaults(func=cmd_owner)

    avatar_parser = sub.add_parser("avatar", parents=[common])
    avatar_parser.add_argument("uin", metavar="<uin>")
    avatar_mode = avatar_parser.add_mutually_exclusive_group()
    avatar_mode.add_argument("--chafa", action="store_true")
    avatar_mode.add_argument("--ascii", action="store_true")
    avatar_parser.set_defaults(func=cmd_avatar)

    sub.add_parser("legacy", aliases=["l"], parents=[common]).set_defaults(func=cmd_legacy)
    sub.add_parser("help", parents=[common]).set_defaults(func=cmd_help)

    args = parser.parse_args()
    args.user = getattr(args, "user", None)
    args.qq = getattr(args, "qq", None)
    args.root_dir = getattr(args, "root_dir", None)
    args.profile_db = getattr(args, "profile_db", None)
    args.nt_msg_db = getattr(args, "nt_msg_db", None)
    args.output_dir = getattr(args, "output_dir", ".")

    try:
        args.func(args)
    except (AppError, OSError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
