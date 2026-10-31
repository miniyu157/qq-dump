#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _export_legacy(args) -> int:
    script = Path(__file__).resolve().parent / "cli" / "QQRootFastDecrypt" / "main.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--profile-db",
            args.profile_info_db,
            "--nt-msg-db",
            args.nt_msg_db,
            "--output",
            args.output,
            *(["--blackboxprotobuf"] if args.blackboxprotobuf else []),
        ]
    )
    return 0


def _export_c2c(args) -> int:
    script = Path(__file__).resolve().parent / "cli" / "c2c" / "main.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--nt-msg-db",
            args.nt_msg_db,
            "--output",
            args.output,
            *(["--blackboxprotobuf"] if args.blackboxprotobuf else []),
        ]
    ).returncode


def _exit_menu(args) -> None:
    return None


MENUS = [
    ("1", "推荐: 经典 QQRootFastDecrypt 聊天记录导出工具", _export_legacy),
    ("2", "遗留功能: 根据 proto_maps.py 映射导出 C2C 消息为 JSONL", _export_c2c),
    ("q", "退出", _exit_menu),
]


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
QQ DUMP 的 Legacy 菜单

Github: https://github.com/miniyu157/qq-dump
""",
    )
    parser.add_argument("-p", "--profile-db", dest="profile_info_db", required=True, help="profile_info.db 路径")
    parser.add_argument("-n", "--nt-msg-db", required=True, help="nt_msg.db 路径")
    parser.add_argument("-o", "--output", required=True, help="输出结果文件的文件夹路径。")
    parser.add_argument("--blackboxprotobuf", action="store_true", help="经典导出器与 C2C JSONL 本次使用旧解析器。")
    return parser.parse_args()


def check_paths(args):
    if not os.path.isdir(args.output):
        sys.exit(f"错误: 没有那个文件夹: '{args.output}'")

    for label, path in (("profile_info.db", args.profile_info_db), ("nt_msg.db", args.nt_msg_db)):
        if not os.path.isfile(path):
            sys.exit(f"错误: {label} 不存在或不是文件: '{path}'")


def push_screen():
    """把当前屏幕内容推入滚动缓冲区，光标回到左上角；效果等同清屏，但旧内容仍可向上翻看"""
    rows = shutil.get_terminal_size().lines
    # 光标在第 r 行时，前 rows - r 个换行移到底部，其余 r 个换行逐行滚动，正好推走全部旧内容
    print("\n" * rows + "\033[H", end="", flush=True)


def print_menu(args):
    menu_items = "\n".join(f"  \033[2;3m{key}\033[0m {title}" for key, title, _ in MENUS)
    separator = f"\033[90m{'─' * shutil.get_terminal_size().columns}\033[0m"
    print(f"""
  \033[1mQQ DUMP 的 Legacy 菜单\033[0m

  \033[4mhttps://github.com/miniyu157/qq-dump\033[0m
  \033[4mhttps://github.com/miniyu157/QQRootFastDecrypt\033[0m

  \033[2m资料库: \033[1m{args.profile_info_db}\033[0m
  \033[2m消息库: \033[1m{args.nt_msg_db}\033[0m
  \033[2m输出文件夹: \033[1m{os.path.abspath(args.output)}\033[0m
  \033[2m当前使用的解析器: \033[1m{'blackboxprotobuf 库' if args.blackboxprotobuf else 'legacy_protobuf.py'}\033[0m

{menu_items}
{separator}""")


def read_line() -> str | None:
    try:
        with open("/dev/tty") as tty:
            return tty.readline()
    except OSError:
        return sys.stdin.readline()


def read_choice() -> str | None:
    print("选择: ", end="", flush=True)
    line = read_line()
    return line.strip() if line else None


def wait_enter():
    print("按回车返回菜单。", end="", flush=True)
    read_line()
    print()


def menu(args) -> int:
    """显示交互菜单；动作返回状态码，返回 None 时结束菜单并保留上次状态码。"""
    actions = {key: action for key, _, action in MENUS}
    rc = 0

    while True:
        push_screen()
        print_menu(args)
        choice = read_choice()

        if choice is None:
            break

        if choice not in actions:
            print(f"错误: 无效的选择: '{choice}'", file=sys.stderr)
            continue

        print()
        try:
            result = actions[choice](args)
            if result is None:
                break
            rc = result
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
            rc = 1
        wait_enter()

    return rc


def main() -> int:
    args = parse_args()
    check_paths(args)
    return menu(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
