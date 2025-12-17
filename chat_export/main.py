import sqlite3
import os
import termios
import tty
import atexit
import base64
from datetime import datetime
from pathlib import Path
import subprocess

# import re
import json
import argparse
import sys
import warnings

# import hashlib
# import html


def cleanup():
    pass


atexit.register(cleanup)


BASE_DIR = Path(__file__).resolve().parent

try:
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
    import blackboxprotobuf

    from rich import print
    from rich.console import Console
    from rich.progress import track
    from rich.rule import Rule

    console = Console()
except ImportError:
    print("使用 'pip install -r requirements.txt' 安装缺少的依赖包。")
    sys.exit(1)


def error(msg: str) -> None:
    print(f"[bold red]错误[/bold red]: {msg}", file=sys.stderr)


def msg1(msg: str) -> None:
    print(f"[bold green]➜ [/bold green]{msg}")


def msg2(msg: str) -> None:
    print(f"[bold green]  ➜ [/bold green]{msg}")


# 消息数据库中的 protobuf 字典
try:
    from proto_maps import PROTO_FIELD_MAP, MSG_TYPE_MAP, IGNORE_IDS
except ImportError:
    error("缺少 proto_maps.py")
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
    return ch


def wait_any_key():
    print("按任意键继续...", end="", flush=True)
    get_key()
    print()


DB_MSG = "nt_msg.db"  # 消息数据库

# C2C单聊消息表
Table_C2c_msg = "c2c_msg_table"

Col_sender_uid = "40020"  # 发送者UID(少数时候会与 40021 相等, 则为自己发出的消息; 如果为空则是系统消息)
Col_peer_uid = "40021"  # 接受者UID
Col_timespan = "40050"  # 秒级消息时间戳
Col_msg = "40800"  # 消息内容, 多层套娃的 Protobuf


# 群聊消息表, 暂不处理
Table_group_msg = "group_msg_table"


DB_PROFILE = "profile_info.db"  # 用户信息数据库
# 存储分组信息和主人UID的表, 一般只有一行
# 列 1000(主人UID), 25011(protobuf 分组信息)
# 二进制 25011 内部结构: 25007(分组ID,0为'我的好友'), 25008(分组名称)
Table_category_list = "category_list_v2"
# 用户信息贮藏表
# 列 1000(UID), 1001(QID,NULL?), 1002(QQ),
# 20002(昵称), 20009(主人设置的备注,NULL?), 20011(个性签名,NULL?)
Table_profile_info = "profile_info_v6"
# 好友列表
# 列 1000(UID), 25007(分组ID)
Table_buddy_list = "buddy_list_v2"


def parseArgs():
    TITLE = """
QQNT DUMP CHAT

Github: https://github.com/miniyu157/qq-dump
"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=TITLE
    )
    parser.add_argument(
        "--input", required=True, help=f"文件夹, 存放 {DB_MSG},{DB_PROFILE}"
    )
    parser.add_argument("--output", required=True, help="输出结果文件的文件夹路径。")
    return parser.parse_args()


# 递归嵌套 protobuf
def recursive_decode(data):
    if not isinstance(data, (bytes, bytearray)):
        return data

    if len(data) == 0:
        return data

    try:
        message, _ = blackboxprotobuf.decode_message(data)

        decoded_message = {}
        for key, value in message.items():
            if isinstance(value, list):
                decoded_message[key] = [recursive_decode(item) for item in value]
            else:
                decoded_message[key] = recursive_decode(value)
        return decoded_message
    except Exception:
        return data


def json_serializer(obj):
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return "BASE64:" + base64.b64encode(obj).decode("ascii")
    return str(obj)


def map_protobuf_keys(data):
    """
    递归将 protobuf 的数字 key 转换为可读字符串，
    并对特定的枚举值进行翻译。
    """
    if isinstance(data, list):
        return [map_protobuf_keys(item) for item in data]

    if not isinstance(data, dict):
        return data

    new_data = {}
    for key, value in data.items():
        key_str = str(key)

        # 过滤极少量的长短字段
        if key_str in IGNORE_IDS or len(key_str) != 5:
            continue

        # 如果在映射表中，使用可读名称；否则保留原始 ID
        readable_key = PROTO_FIELD_MAP.get(key_str, key_str)
        processed_value = map_protobuf_keys(value)

        match readable_key:
            case "MSG_TYPE":
                if isinstance(processed_value, int):
                    processed_value = MSG_TYPE_MAP.get(processed_value, processed_value)

            case _:
                pass

        # # 翻译消息类型
        # if key_str == "45002" and isinstance(processed_value, int):
        # processed_value = MSG_TYPE_MAP.get(processed_value, processed_value)

        # # 强制将某些肯定是文本的 bytes 字段转为 str
        # # blackboxprotobuf 有时会把 utf-8 文本误判为 bytes
        # text_fields = ["45101", "47602", "45402", "47413", "80900"]
        # if key_str in text_fields and isinstance(processed_value, bytes):
        # try:
        # processed_value = processed_value.decode("utf-8")
        # except:
        # pass  # 解码失败保持原样

        new_data[readable_key] = processed_value

    return new_data


def fn_export_c2c():
    db_msg = os.path.join(args.input, DB_MSG)
    db_profile = os.path.join(args.input, DB_PROFILE)

    output_file_path = os.path.join(args.output, "parsed_messages.txt")

    conn = None
    try:
        conn = sqlite3.connect(db_msg)
        cursor = conn.cursor()

        msg1("正在统计...")
        cursor.execute(f"SELECT COUNT(*) FROM {Table_C2c_msg}")
        total_count = cursor.fetchone()[0]

        # 查询 C2C 消息表
        query = f'SELECT "{Col_timespan}", "{Col_sender_uid}", "{Col_peer_uid}", "{Col_msg}" FROM {Table_C2c_msg} ORDER BY "{Col_timespan}" ASC'

        cursor.execute(query)

        msg1("导出 C2C 消息...")
        with open(output_file_path, "w", encoding="utf-8") as f_out:
            count = 0
            for row in track(cursor, total=total_count, description=" "):
                ts, sender, peer, msg_blob = row
                if not sender:
                    sender = "[系统提示]"
                if sender == peer:
                    sender = "u_MyUID"
                try:
                    dt_object = datetime.fromtimestamp(int(ts))
                    time_str = f"{dt_object:%Y-%m-%d %H:%M:%S} ({ts})"
                except (ValueError, TypeError):
                    time_str = str(ts)

                # 递归解析数据
                # decoded_struct = recursive_decode(msg_blob)
                raw_decoded = recursive_decode(msg_blob)
                decoded_struct = map_protobuf_keys(raw_decoded)

                json_content = json.dumps(
                    decoded_struct,
                    ensure_ascii=False,
                    default=json_serializer,
                    indent=2,
                )

                # 构造输出行
                line = f"[{time_str}] {sender} -> {peer}\n{json_content}\n"
                f_out.write(line)

                count += 1

        msg1(f"共导出 {count} 条消息到 {output_file_path}")

    except sqlite3.Error as e:
        error(f"SQLite: {e}")
    except Exception as e:
        error(f"{e}")
    finally:
        if conn:
            conn.close()


def start_old_script(*args):
    script = BASE_DIR / "old.py"
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        args = args[0]

    subprocess.run([sys.executable, script, *args])


def init_ui():
    console.clear()
    head = f"""
[bold]QQNT DUMP CHAT [yellow]ᴀʟᴘʜᴀ[/yellow][/bold]

Github: https://github.com/miniyu157/qq-dump

输入: {args.input}
输出: {args.output}
"""
    console.print(head, justify="center")
    console.print(Rule(style="white"))


def menu_loop():
    while True:
        init_ui()

        print(
            """
   [1] 旧 QQRootFastDecrypt
   [2] 旧 QQRootFastDecrypt 帮助信息
   [3] [Lab] 导出 C2C 消息
   [Q] 退出
        """
        )
        print("等待按下按键: ", end="", flush=True)
        choice = get_key().upper()
        actions = {
            "Q": lambda: (print("\nBye."), sys.exit(0)),
            "3": lambda: (init_ui(), fn_export_c2c(), print(), wait_any_key()),
            "2": lambda: (
                init_ui(),
                start_old_script("--help"),
                print(),
                wait_any_key(),
            ),
            "1": lambda: (
                init_ui(),
                start_old_script(*sys.argv[1:]),
                print(),
                wait_any_key(),
            ),
        }
        actions.get(choice, lambda: None)()


def main():
    if not os.path.exists(args.output) or not os.path.isdir(args.output):
        error(f"没有那个文件夹: '{args.output}'")
        sys.exit(1)

    db_msg = os.path.join(args.input, DB_MSG)
    db_profile = os.path.join(args.input, DB_PROFILE)

    if not os.path.exists(db_msg):
        error(f"'{args.input}' 中未找到 '{DB_MSG}'")
        sys.exit(1)

    if not os.path.exists(db_profile):
        error(f"'{args.input}' 中未找到 '{DB_PROFILE}'")
        sys.exit(1)

    menu_loop()


if __name__ == "__main__":
    global args
    args = parseArgs()

    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        error(f"未捕获的异常: {e}")
        # sys.exit(1)
