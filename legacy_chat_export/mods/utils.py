import os
import subprocess
import sys
import termios
import tty
import argparse

from . import msg as msg
from . import schema as dbsma


def parseArgs():
    TITLE = """
QQNT DUMP CHAT

Github: https://github.com/miniyu157/qq-dump
"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=TITLE
    )
    parser.add_argument(
        "--input", required=True, help=f"文件夹, 存放 {dbsma.DB_MSG},{dbsma.DB_PROFILE}"
    )
    parser.add_argument("--output", required=True, help="输出结果文件的文件夹路径。")
    return parser.parse_args()


def check_paths(args):
    if not os.path.exists(args.output) or not os.path.isdir(args.output):
        msg.error(f"没有那个文件夹: '{args.output}'")
        sys.exit(1)

    db_msg = os.path.join(args.input, dbsma.DB_MSG)
    db_profile = os.path.join(args.input, dbsma.DB_PROFILE)

    if not os.path.exists(db_msg):
        msg.error(f"'{args.input}' 中未找到 '{dbsma.DB_MSG}'")
        sys.exit(1)

    if not os.path.exists(db_profile):
        msg.error(f"'{args.input}' 中未找到 '{dbsma.DB_PROFILE}'")
        sys.exit(1)


def get_key() -> str:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def wait_any_key():
    msg.print("[green]按任意键继续...[/green]", end="", flush=True)
    get_key()
    msg.print()


def start_new_py(script, *args):
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        args = args[0]

    subprocess.run([sys.executable, script, *args])
