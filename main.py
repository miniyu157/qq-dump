#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

from api.errors import DatabaseError
from app.ansi import err, out
from app.errors import AppError
from app.utils import cancel_log, require_binaries, require_modules, warn_log
from app.version import version

SCRIPT_DIR = Path(__file__).resolve().parent

# 版本串开头的发布 tag；要求其后为分隔符或结尾，避免把 v0.1.10 截成 v0.1.1
VERSION_TAG = re.compile(r"v\d+(?:\.\d+)*(?=$|[- ])")


def cmd_key(args: argparse.Namespace) -> None:
    """输出可用的密钥记录；被跳过的账号由 get_keys.py 警告，不影响退出码。"""
    from app.accounts import prepare_access, valid_keys
    from app.output import render_json
    from app.scripts import get_keys

    as_root = prepare_access(args.root_dir, args.user, decrypting=False)
    render_json(valid_keys(get_keys(args.user, args.qq, args.root_dir, as_root=as_root)))


def cmd_db(args: argparse.Namespace) -> None:
    """获取密钥，再逐账号解密。"""
    from app.accounts import prepare_access, valid_keys
    from app.scripts import decrypt, get_keys

    as_root = prepare_access(args.root_dir, args.user, decrypting=True)
    records = valid_keys(get_keys(args.user, args.qq, args.root_dir, as_root=as_root))

    # 账号字段在此展开；{filename} 留给 decrypt_db.py 按实际文件名填充。全部展开成功后才开始解密
    try:
        name_formats = [args.name_format.format(**record, filename="{filename}") for record in records]
    except (KeyError, IndexError, ValueError) as exc:
        raise AppError(f"--name-format 模版无效: {args.name_format} ({exc})") from exc

    failed = False
    for record, name_format in zip(records, name_formats, strict=True):
        if not decrypt(record, args.output_dir, name_format, args.files, skip_empty=args.skip_empty, as_root=as_root):
            failed = True

    if failed:
        sys.exit(1)


def cmd_avatar(args: argparse.Namespace) -> None:
    """获取并渲染指定 UIN 的头像；--chafa 交给 chafa，--ascii 使用真彩色字符画。"""
    from app.dependencies import CHAFA, PILLOW
    from service.avatars import avatar, prepare_cache

    if args.chafa:
        require_binaries("使用 chafa 查看头像", [CHAFA])
    else:
        # 默认渲染与 --ascii 都经 lib.tui.image，依赖 pillow
        require_modules("渲染头像", [PILLOW])

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
    from app.databases import complete_databases, print_database_hint

    databases = [("profile_db", "profile_info.db")]
    print_database_hint(args, databases, purpose="WebUI 功能")
    complete_databases(args, databases)

    from web.server import serve

    serve(args.profile_db, args.nt_msg_db)


def cmd_friends(args: argparse.Namespace) -> None:
    """输出好友 JSON。"""
    from app.databases import complete_databases, print_database_hint
    from app.output import render_json

    databases = [("profile_db", "profile_info.db")]
    print_database_hint(args, databases)
    complete_databases(args, databases)

    from api import load_friends

    render_json(friend._asdict() for friend in load_friends(args.profile_db))


def cmd_owner(args: argparse.Namespace) -> None:
    """输出主人信息。"""
    from app.databases import complete_databases, print_database_hint
    from app.output import render_json

    databases = [("profile_db", "profile_info.db")]
    print_database_hint(args, databases)
    complete_databases(args, databases)

    from api import load_owner

    owner = load_owner(args.profile_db)
    render_json(owner._asdict() if owner is not None else None)


def cmd_legacy(args: argparse.Namespace) -> None:
    """补全缺失数据库后启动 legacy。"""
    from app.databases import complete_databases, print_database_hint

    databases = [("profile_db", "profile_info.db"), ("nt_msg_db", "nt_msg.db")]
    print_database_hint(args, databases, purpose="Legacy 功能")
    complete_databases(args, databases)

    legacy_main = SCRIPT_DIR / "legacy-cli" / "main.py"
    command = [sys.executable, str(legacy_main), "-p", args.profile_db, "-n", args.nt_msg_db, "-o", args.output_dir]
    if getattr(args, "blackboxprotobuf", False):
        command.append("--blackboxprotobuf")
    proc = subprocess.run(command, check=False)
    raise SystemExit(proc.returncode)


def cmd_tealina28_qqnt_export(args: argparse.Namespace) -> None:
    """检查外部项目环境，补全缺省的数据库目录后启动 t28，传播导出器退出码。"""
    from app.databases import complete_database_dir
    from app.integrations.t28 import check_environment as check_t28_environment
    from app.integrations.t28 import run as run_t28

    check_t28_environment()
    if args.db_dir is None:
        names = ", ".join(f"{err.HL}{name}{err.RESET}" for name in ("profile_info.db", "nt_msg.db", "group_info.db"))
        print(f"Tealina28/QQNT_Export 功能需要数据库: {names}\n也可以使用 {err.HL}--db-dir{err.RESET} 预先设置数据库目录\n", file=sys.stderr)
    complete_database_dir(
        args,
        attr="db_dir",
        databases=["profile_info.db", "nt_msg.db", "group_info.db"],
    )
    raise SystemExit(run_t28(db_dir=args.db_dir, output_dir=args.output_dir))


def cmd_check(args: argparse.Namespace) -> None:
    """检查运行时依赖，按二进制与 Python 模块分类列出结果；依赖均为可选，缺失不影响退出码。"""
    from app.dependencies import BINARIES, MODULES
    from app.utils import binary_found, module_found

    # 显示 pip 包名，按导入名检查
    groups = (
        ("二进制依赖", [(binary.name, binary.purpose, binary_found(binary)) for binary in BINARIES]),
        ("Python 依赖", [(module.package, module.purpose, module_found(module)) for module in MODULES]),
    )

    print(f"{err.BOLD}QQ DUMP 依赖检查{err.RESET}", file=sys.stderr)
    for label, results in groups:
        print(file=sys.stderr)
        print(label, file=sys.stderr)
        for name, purpose, found in results:
            color, status = (err.GOOD, "已找到") if found else (err.ERR, "未找到")
            print(f"{err.BOLD}{color}● {status}{err.RESET} {name} {err.FAINT}({purpose}){err.RESET}", file=sys.stderr)
    results = [result for _, items in groups for result in items]
    missing = sum(not found for *_, found in results)
    print(f"\n共计: {len(results)} 项, 缺失: {missing} 项", file=sys.stderr)


def cmd_help(args: argparse.Namespace) -> None:
    sys.stdout.write(help_text())


def cmd_menu(args: argparse.Namespace) -> None:
    """无子命令时显示主菜单。"""
    from lib.tui.choose import ChoiceCancelled, choose

    title = (
        f"{err.BOLD}QQ DUMP TUI{err.RESET} {styled_version(err)}{err.RESET}\n"
        f"{err.PINK}https://github.com/miniyu157/qq-dump{err.RESET}\n\n"
        f"{err.BOLD}{err.INFO}今天想要做些什么?{err.RESET}"
    )
    menu = (
        ("运行 WebUI 服务器", cmd_web),
        ("运行 Legacy 消息导出", cmd_legacy),
        ("运行 Tealina28/QQNT_Export", cmd_tealina28_qqnt_export),
        ("查看 CLI 帮助", cmd_help),
        ("运行依赖检查", cmd_check),
    )
    try:
        choice = choose([label for label, _ in menu], title=title)
    except (ChoiceCancelled, EOFError):
        cancel_log("无事发生")
        sys.exit(1)
    except ValueError as exc:
        warn_log(str(exc))
        sys.exit(1)
    menu[choice][1](args)


def styled_version(styles) -> str:
    """开头的 tag 显示为普通色，之后的部分显示为灰色，末尾以 RESET 结束；不以 tag 开头时原样返回"""
    text = version()
    match = VERSION_TAG.match(text)
    if not match:
        return text
    tag = match.group()
    return f"{tag}{styles.GRAY}{text[len(tag):]}{styles.RESET}"


def help_text() -> str:
    """返回唯一的帮助文本；-h、help 子命令与 argparse 共用。"""
    prog = Path(sys.argv[0]).name
    _title = "\033[1;4m" if out.TTY else ""
    return f"""{out.BOLD}QQ DUMP -- 从 NTQQ 数据库得到信息{out.RESET}
{styled_version(out)}

  {out.FAINT}tip: 所需的数据库文件 (-p/-n) 或目录 (--db-dir) 未提供时，
  会显示账号选择界面，并即时解密补齐。{out.RESET}

{_title}用法:{out.RESET}
  {out.BOLD}{prog}{out.RESET} [选项] [子命令=menu] [命令选项] [参数]

{_title}选项 (全局):{out.RESET}
  {out.BOLD}-u, --user <ID>{out.RESET}                       Android 用户 ID{out.RESET}
  {out.BOLD}-a, --qq <uin/uid>{out.RESET}                    QQ uin 或 uid 文本{out.RESET}
  {out.BOLD}-r, --root-dir <目录=/>{out.RESET}               扫描根目录 {out.FAINT}(默认: /){out.RESET}
  {out.BOLD}-p, --profile-db <路径>{out.RESET}               profile_info.db 路径{out.RESET}
  {out.BOLD}-n, --nt-msg-db <路径>{out.RESET}                nt_msg.db 路径{out.RESET}
  {out.BOLD}-o, --output-dir <目录=.>{out.RESET}             输出目录 {out.FAINT}(默认: 当前目录){out.RESET}

{_title}子命令 (解密):{out.RESET}
  {out.HL}key{out.RESET} {out.FAINT}[-u] [-a] [-r]{out.RESET}                    为选定用户计算数据库密钥
  {out.HL}db{out.RESET} {out.FAINT}[-o] [-u] [-a] [-r]{out.RESET} [files...]     为选定用户解密数据库文件
    {out.BOLD}-f, --name-format <模版>{out.RESET}            输出文件名模版，斜杠表示目录层
                                        {out.FAINT}(默认: {{user}}.{{uin}}/{{filename}}){out.RESET}
    {out.BOLD}--skip-empty{out.RESET}                        跳过文件过小的数据库

{_title}子命令 (解析与导出):{out.RESET}
  {out.HL}web{out.RESET} {out.FAINT}[-p]{out.RESET}                              启动本地 WebUI
  {out.HL}friends{out.RESET} {out.FAINT}[-p]{out.RESET}                          输出好友 JSON
  {out.HL}owner{out.RESET} {out.FAINT}[-p]{out.RESET}                            输出主人信息
  {out.HL}l, legacy{out.RESET} {out.FAINT}[-o] [-n] [-p]{out.RESET}              启动 legacy 菜单
    {out.BOLD}--blackboxprotobuf{out.RESET}                  使用旧 protobuf 解析器
  {out.HL}t28, Tealina28-QQNT_Export{out.RESET} {out.FAINT}[-o]{out.RESET}       Tealina28/QQNT_Export 消息导出
    {out.BOLD}--db-dir <目录>{out.RESET}                     数据库目录

{_title}子命令 (其它):{out.RESET}
  {out.HL}menu{out.RESET}                                  显示主菜单
  {out.HL}check{out.RESET}                                 检查运行时依赖
  {out.HL}avatar{out.RESET} <uin>                          根据官方 API 获取头像并渲染
    {out.BOLD}--chafa{out.RESET}                             改用 chafa 渲染头像
    {out.BOLD}--ascii{out.RESET}                             改用真彩色 ASCII 字符画

{_title}环境变量:{out.RESET}
  {out.FAINT}命令行参数优先，其次为进程环境变量，再次为仓库根目录的 .env;
  .env 中的相对路径按仓库根目录解析，开关类变量取值 1/true/yes/on 为开启;{out.RESET}
  {out.BOLD}QQDUMP_ROOT_DIR{out.RESET}                       同 -r, --root-dir
  {out.BOLD}QQDUMP_PROFILE_DB{out.RESET}                     同 -p, --profile-db
  {out.BOLD}QQDUMP_NT_MSG_DB{out.RESET}                      同 -n, --nt-msg-db
  {out.BOLD}QQDUMP_SUDO_NOTICE{out.RESET}                    同 -s, --[no-]sudo-notice
  {out.BOLD}QQDUMP_VERBOSE{out.RESET}                        同 -v, --[no-]verbose

{_title}选项 (调试):{out.RESET}
  {out.BOLD}-s, --[no-]sudo-notice{out.RESET}                提权执行前显示提示 {out.FAINT}(默认: 关闭){out.RESET}
  {out.BOLD}-v, --[no-]verbose{out.RESET}                    显示详细调试信息 {out.FAINT}(默认: 关闭){out.RESET}
  {out.BOLD}-E, --ignore-env{out.RESET}                      忽略环境变量与 .env

{_title}选项 (程序):{out.RESET}
  {out.BOLD}-h, --help{out.RESET}                            显示本帮助{out.RESET}
  {out.BOLD}-V, --version{out.RESET}                         显示版本号
"""


class VersionAction(argparse.Action):
    """触发时才读取版本，避免每次启动都执行 git 子进程"""

    def __init__(self, option_strings: list[str], dest: str, **kwargs: object) -> None:
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS)

    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, values: object, option_string: str | None = None) -> None:
        print(styled_version(out))
        parser.exit()


class HelpParser(argparse.ArgumentParser):
    """帮助文本自持，argparse 只负责 -h 的触发与退出"""

    def format_help(self) -> str:
        """始终返回同一份帮助，忽略子解析器的 prog。"""
        return help_text()


def main() -> None:
    """程序入口：装配解析器并分发到对应子命令。"""
    from app.config import resolve_options
    from app.scripts import set_sudo_notice, set_verbose

    # Windows 重定向时默认按 ANSI 代码页编码，中文输出与 UTF-8 下游不一致；控制台输出不受影响
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    common = argparse.ArgumentParser(add_help=False)
    # 公共选项可位于子命令前后；SUPPRESS 防止子解析器默认值覆盖此前已解析的取值
    common.add_argument("-u", "--user", default=argparse.SUPPRESS)
    common.add_argument("-a", "--qq", default=argparse.SUPPRESS)
    common.add_argument("-r", "--root-dir", dest="root_dir", default=argparse.SUPPRESS)
    common.add_argument("-p", "--profile-db", dest="profile_db", default=argparse.SUPPRESS)
    common.add_argument("-n", "--nt-msg-db", dest="nt_msg_db", default=argparse.SUPPRESS)
    common.add_argument("-s", "--sudo-notice", dest="sudo_notice", action=argparse.BooleanOptionalAction, default=argparse.SUPPRESS)
    common.add_argument("-o", "--output-dir", dest="output_dir", default=argparse.SUPPRESS)
    common.add_argument("-v", "--verbose", dest="verbose", action=argparse.BooleanOptionalAction, default=argparse.SUPPRESS)
    common.add_argument("-E", "--ignore-env", dest="ignore_env", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("-V", "--version", action=VersionAction)

    parser = HelpParser(parents=[common])
    # 未指定子命令时显示菜单
    parser.set_defaults(func=cmd_menu)
    sub = parser.add_subparsers(dest="command", parser_class=HelpParser)
    sub.add_parser("key", parents=[common]).set_defaults(func=cmd_key)
    db_parser = sub.add_parser("db", parents=[common])
    db_parser.add_argument("files", nargs="*")
    db_parser.add_argument("-f", "--name-format", default="{user}.{uin}/{filename}")
    db_parser.add_argument("--skip-empty", action="store_true")
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

    legacy_parser = sub.add_parser("legacy", aliases=["l"], parents=[common])
    legacy_parser.add_argument("--blackboxprotobuf", action="store_true")
    legacy_parser.set_defaults(func=cmd_legacy)
    t28_parser = sub.add_parser("Tealina28-QQNT_Export", aliases=["t28"], parents=[common])
    t28_parser.add_argument("--db-dir")
    t28_parser.set_defaults(func=cmd_tealina28_qqnt_export)
    sub.add_parser("help", parents=[common]).set_defaults(func=cmd_help)
    sub.add_parser("menu", parents=[common]).set_defaults(func=cmd_menu)

    args = parser.parse_args()
    resolve_options(args)
    set_sudo_notice(args.sudo_notice)
    set_verbose(args.verbose)

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
