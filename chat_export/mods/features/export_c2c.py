import sqlite3
import json
import os
from datetime import datetime
import base64
import sys
import warnings

import mods.schema as dbsma
import mods.msg as msg

META = {"key": "3", "title": "[Dev] 导出 C2C 消息", "order": 3}

try:
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
    import blackboxprotobuf

except ImportError:
    msg.print("使用 'pip install -r requirements.txt' 安装缺少的依赖包。")
    sys.exit(1)


# 消息数据库中的 protobuf 字典
try:
    from proto_maps import PROTO_FIELD_MAP, MSG_TYPE_MAP, IGNORE_IDS
except ImportError:
    msg.error("缺少 proto_maps.py")
    sys.exit(1)


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

        new_data[readable_key] = processed_value

    return new_data


def run(args):
    db_msg = os.path.join(args.input, dbsma.DB_MSG)
    db_profile = os.path.join(args.input, dbsma.DB_PROFILE)

    output_file_path = os.path.join(args.output, "parsed_messages.txt")
    conn = None
    try:
        conn = sqlite3.connect(db_msg)
        cursor = conn.cursor()

        msg.msg1("正在统计...")
        cursor.execute(f"SELECT COUNT(*) FROM {dbsma.Table_C2c_msg}")
        total_count = cursor.fetchone()[0]

        # 查询 C2C 消息表
        query = f'SELECT "{dbsma.Col_timespan}", "{dbsma.Col_sender_uid}", "{dbsma.Col_peer_uid}", "{dbsma.Col_msg}" FROM {dbsma.Table_C2c_msg} ORDER BY "{dbsma.Col_timespan}" ASC'
        cursor.execute(query)

        msg.msg1("导出 C2C 消息...")
        with open(output_file_path, "w", encoding="utf-8") as f_out:
            count = 0
            for row in msg.track(cursor, total=total_count, description=" "):
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

        msg.msg1(f"共导出 {count} 条消息到 {output_file_path}")

    except sqlite3.Error as e:
        msg.error(f"SQLite: {e}")
    except Exception as e:
        msg.error(f"{e}")
    finally:
        if conn:
            conn.close()
