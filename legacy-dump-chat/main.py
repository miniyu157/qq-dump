#!/usr/bin/env python3

import argparse
import os
import shutil
import sys

import c2c
import legacy

MENUS = [
    ("1", "聊天记录导出工具", legacy.run),
    ("2", "[Dev] 导出 C2C 消息", c2c.run),
]


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
QQNT DUMP CHAT (Legacy)

Github: https://github.com/miniyu157/qq-dump
""",
    )
    parser.add_argument("-p", "--profile-db", dest="profile_info_db", required=True, help="profile_info.db 路径")
    parser.add_argument("-n", "--nt-msg-db", required=True, help="nt_msg.db 路径")
    parser.add_argument("-o", "--output", required=True, help="输出结果文件的文件夹路径。")
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
    print("QQNT DUMP CHAT (Legacy)\n")
    print("Github: https://github.com/miniyu157/qq-dump\n")
    print(f"资料库: {args.profile_info_db}")
    print(f"消息库: {args.nt_msg_db}")
    print(f"输出: {args.output}\n")
    for key, title, _ in MENUS:
        print(f"  [{key}] {title}")
    print("  [Q] 退出\n")


def read_line() -> str | None:
    try:
        with open("/dev/tty") as tty:
            return tty.readline()
    except OSError:
        return sys.stdin.readline()


def read_choice() -> str | None:
    print("选择: ", end="", flush=True)
    line = read_line()
    return line.strip().upper() if line else None


def wait_enter():
    print("按回车返回菜单。", end="", flush=True)
    read_line()
    print()


def menu(args) -> int:
    tasks = {key: run for key, _, run in MENUS}
    rc = 0

    while True:
        push_screen()
        print_menu(args)
        choice = read_choice()

        if choice is None or choice == "Q":
            break

        if choice not in tasks:
            print(f"错误: 无效的选择: '{choice}'", file=sys.stderr)
            continue

        print()
        try:
            rc = tasks[choice](args) or 0
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
