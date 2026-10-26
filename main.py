#!/usr/bin/env python3
import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from api.errors import DatabaseError
from app.ansi import err, out
from app.databases import complete_databases
from app.errors import AppError
from app.output import render_json
from app.scripts import decrypt, get_keys, print_keys, qq_data_accessible, require_qq_data
from app.utils import require_binaries, require_modules
from lib.tui.choose import choose

VERSION = "0.1.2"

SCRIPT_DIR = Path(__file__).resolve().parent


def cmd_key(args: argparse.Namespace) -> None:
    """调用 get_keys.py 输出密钥记录。"""
    require_qq_data(args.root_dir, args.user)
    as_root = not qq_data_accessible(args.root_dir, args.user)
    raise SystemExit(print_keys(args.user, args.qq, args.root_dir, as_root=as_root))


def cmd_db(args: argparse.Namespace) -> None:
    """获取密钥，再逐账号解密。"""
    require_binaries("数据库解密", ["sqlcipher"])
    require_qq_data(args.root_dir, args.user)
    as_root = not qq_data_accessible(args.root_dir, args.user)

    failed = False
    for record in get_keys(args.user, args.qq, args.root_dir, as_root=as_root):
        # 账号字段在此展开；{filename} 留给 decrypt_db.py 按实际文件名填充
        name_format = args.name_format.format(**record, filename="{filename}")
        if not decrypt(record, args.output_dir, name_format, args.files, as_root=as_root):
            failed = True

    if failed:
        sys.exit(1)


def cmd_avatar(args: argparse.Namespace) -> None:
    """获取并渲染指定 UIN 的头像；--chafa 交给 chafa，--ascii 使用真彩色字符画。"""
    from service.avatars import avatar, prepare_cache

    if args.chafa:
        require_binaries("使用 chafa 查看头像", ["chafa"])
    else:
        require_modules("渲染头像", ["PIL"])

    prepare_cache()
    try:
        result = avatar(args.uin)
    except ValueError as exc:
        raise AppError(str(exc)) from exc
    if result is None:
        raise AppError(f"无法获取头像，网络请求失败且无缓存: {args.uin}")
    data, _ = result
    if args.chafa:
        proc = subprocess.run(["chafa", "-"], input=data, check=False)
        raise SystemExit(proc.returncode)

    from lib.tui.image import render

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


def cmd_legacy(args: argparse.Namespace) -> None:
    """检查依赖、补全缺失数据库后启动 legacy。"""
    require_modules("legacy 功能", ["blackboxprotobuf"])
    complete_databases(args, [("profile_db", "profile_info.db"), ("nt_msg_db", "nt_msg.db")])

    legacy_main = SCRIPT_DIR / "legacy-dump-chat" / "main.py"
    proc = subprocess.run([sys.executable, str(legacy_main), "-p", args.profile_db, "-n", args.nt_msg_db, "-o", args.output_dir], check=False)
    raise SystemExit(proc.returncode)


def cmd_check(args: argparse.Namespace) -> None:
    """检查运行时依赖，按二进制与 Python 模块分类列出结果；依赖均为可选，缺失不影响退出码。"""
    binaries = (
        ("sudo", "QQ 数据不可访问时需要"),
        ("sqlcipher", "解密数据库时需要"),
        ("chafa", "运行 avatar --chafa 时需要"),
    )
    # 显示 pip 包名，按导入名检查
    modules = (
        ("blackboxprotobuf", "blackboxprotobuf", "运行 legacy 时需要"),
        ("pillow", "PIL", "运行 avatar 渲染头像时需要"),
    )
    groups = (
        ("二进制依赖", [(name, purpose, shutil.which(name) is not None) for name, purpose in binaries]),
        ("Python 依赖", [(name, purpose, importlib.util.find_spec(module) is not None) for name, module, purpose in modules]),
    )

    print(f"{err.BOLD}QQ DUMP 依赖检查{err.RESET}", file=sys.stderr)
    for label, results in groups:
        print(file=sys.stderr)
        print(label, file=sys.stderr)
        for name, purpose, found in results:
            color, status = (err.GOOD, "已找到") if found else (err.ERR, "未找到")
            print(f"{color}● {status}{err.RESET} {name} {err.FAINT}({purpose}){err.RESET}", file=sys.stderr)
    results = [result for _, items in groups for result in items]
    missing = sum(not found for *_, found in results)
    print(f"\n共计: {len(results)} 项, 缺失: {missing} 项", file=sys.stderr)


def cmd_help(args: argparse.Namespace) -> None:
    sys.stdout.write(help_text())


def cmd_menu(args: argparse.Namespace) -> None:
    """无子命令时显示主菜单。"""
    title = (
        f"{err.BOLD}QQ DUMP TUI v{VERSION}{err.RESET}\n"
        f"{err.HL}https://github.com/miniyu157/qq-dump{err.RESET}\n\n"
        f"{err.INFO}今天想要做些什么?{err.RESET}"
    )
    menu = (
        (f"运行 WebUI 服务器 {err.FAINT}(需要数据库文件){err.RESET}", cmd_web),
        (f"运行 Legacy 消息导出 {err.FAINT}(需要数据库文件){err.RESET}", cmd_legacy),
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
    _title = "\033[1;4m" if out.TTY else ""
    _cmd_a = f"{out.BOLD}{out.HL}"
    return f"""{out.BOLD}QQ DUMP v{VERSION} -- 从 NTQQ 数据库得到信息{out.RESET}

  {out.FAINT}tip: 数据库文件参数 (如 -p/-n) 被需要且未指定时，
  会显示账号选择界面，并即时解密补齐。
  未指定子命令时显示菜单。{out.RESET}

{_title}用法:{out.RESET}
  {out.BOLD}{prog}{out.RESET} [选项] [<子命令>] [命令选项] [参数]

{_title}选项 (全局):{out.RESET}
  {out.BOLD}-u, --user <ID>{out.RESET}                  Android 用户 ID{out.RESET}
  {out.BOLD}-a, --qq <uin/uid>{out.RESET}               QQ uin 或 uid 文本{out.RESET}
  {out.BOLD}-r, --root-dir <目录=/>{out.RESET}          扫描根目录 {out.FAINT}(默认: /){out.RESET}
  {out.BOLD}-p, --profile-db <路径>{out.RESET}          profile_info.db 路径{out.RESET}
  {out.BOLD}-n, --nt-msg-db <路径>{out.RESET}           nt_msg.db 路径{out.RESET}
  {out.BOLD}-o, --output-dir <目录=.>{out.RESET}        输出目录 {out.FAINT}(默认: 当前目录){out.RESET}

{_title}子命令:{out.RESET}
  {_cmd_a}key{out.RESET} [-u] [-a] [-r]               为选定用户计算数据库密钥

  {_cmd_a}db{out.RESET} [-u] [-a] [-r] [-o] [-f] [files...] 为选定用户解密数据库文件
    {out.BOLD}-f, --name-format <模版>{out.RESET}       输出文件名模版，斜杠表示目录层
                                   {out.FAINT}(默认: {{user}}.{{uin}}/{{filename}}){out.RESET}

  {_cmd_a}check{out.RESET}                            检查运行时依赖

  {_cmd_a}web{out.RESET} [-p]                         启动本地 WebUI

  {_cmd_a}friends{out.RESET} [-p]                     输出好友 JSON

  {_cmd_a}owner{out.RESET} [-p]                       输出主人信息

  {_cmd_a}l, legacy{out.RESET} [-p] [-n] [-o]         启动 legacy-dump-chat

  {_cmd_a}avatar{out.RESET} <uin> [--chafa|--ascii]   根据官方 API 获取头像并渲染
    {out.BOLD}--chafa{out.RESET}                        改用 chafa 查看头像
    {out.BOLD}--ascii{out.RESET}                        改用真彩色 ASCII 字符画

{_title}选项 (程序):{out.RESET}
  {out.BOLD}-h, --help{out.RESET}                       显示本帮助{out.RESET}
  {out.BOLD}-v, --version{out.RESET}                    显示版本号
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
    except (AppError, DatabaseError, OSError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
