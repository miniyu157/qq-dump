#!/usr/bin/env python3

import argparse
import base64
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.extend([str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[3])])

from legacy_protobuf import decode_c2c
from c2c.schema import schema
from c2c.schema.proto_maps import IGNORE_IDS, MSG_TYPE_MAP, PROTO_FIELD_MAP


def _load_old_decoder():
    """加载旧递归解码器；缺少可选依赖时抛 ImportError，解码失败时保留原值。"""
    import blackboxprotobuf

    def decode(data):
        if not isinstance(data, (bytes, bytearray)) or not data:
            return data
        try:
            message, _ = blackboxprotobuf.decode_message(data)
            return {key: [decode(item) for item in value] if isinstance(value, list) else decode(value) for key, value in message.items()}
        except Exception:
            return data

    return decode


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

        if readable_key == "MSG_TYPE" and isinstance(processed_value, int):
            processed_value = MSG_TYPE_MAP.get(processed_value, processed_value)

        new_data[readable_key] = processed_value

    return new_data


def run(args, *, decode):
    db_msg = args.nt_msg_db
    output_path = os.path.join(args.output, "messages.jsonl")

    conn = sqlite3.connect(db_msg)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {schema.Table_C2c_msg}")
        total = cursor.fetchone()[0]
        print(f"共 {total} 条 C2C 消息。")

        cursor.execute(f'SELECT "{schema.Col_timespan}", "{schema.Col_sender_uid}", "{schema.Col_peer_uid}", "{schema.Col_msg}" FROM {schema.Table_C2c_msg} ORDER BY "{schema.Col_timespan}" ASC')

        with open(output_path, "w", encoding="utf-8") as f_out:
            count = 0
            for ts, sender, peer, msg_blob in cursor:
                record = {
                    "time": ts,
                    "sender": sender or None,
                    "peer": peer or None,
                    "msg": map_protobuf_keys(decode(msg_blob)),
                }
                line = json.dumps(record, ensure_ascii=False, default=json_serializer)

                f_out.write(line + "\n")

                count += 1
                print(f"\r  解析 {count}/{total}", end="", flush=True)

        print(f"\r  已导出 {count} 条消息到 {output_path}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="根据 proto_maps.py 映射导出 C2C 消息为 JSONL。")
    parser.add_argument("-n", "--nt-msg-db", required=True, help="nt_msg.db 路径")
    parser.add_argument("-o", "--output", required=True, help="输出 messages.jsonl 的文件夹路径。")
    parser.add_argument("--blackboxprotobuf", action="store_true", help="本次使用旧 blackboxprotobuf 解析器；默认使用 legacy_protobuf.py。")
    args = parser.parse_args()

    decode = decode_c2c
    if args.blackboxprotobuf:
        try:
            decode = _load_old_decoder()
        except ImportError as exc:
            parser.error(f"blackboxprotobuf 或其依赖不可用 ({exc})；请安装 blackboxprotobuf。")

    if not os.path.isfile(args.nt_msg_db):
        sys.exit(f"错误: nt_msg.db 不存在或不是文件: '{args.nt_msg_db}'")
    if not os.path.isdir(args.output):
        sys.exit(f"错误: 没有那个文件夹: '{args.output}'")

    run(args, decode=decode)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
