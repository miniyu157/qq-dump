"""与数据库、终端无关的值格式化：Protobuf 解码、BLOB 表示、时间与 JSON 标量。"""

import json
from datetime import datetime

from lib.wire import as_text, parse_fields


def decode(buf, depth=0, *, max_depth):
    """按线格式解码；max_depth 为消息递归上限，文本字段提前返回，不消耗层级。"""
    if not buf:
        return ""
    text = as_text(buf)
    if text is not None:
        return text
    if depth >= max_depth:
        return {"_hex": buf.hex()}
    fields = parse_fields(buf)
    if not fields:
        return {"_hex": buf.hex()}
    out = {}
    for num, wire, val in fields:
        if wire == "varint":
            value = val
        elif wire == "bytes":
            value = decode(val, depth + 1, max_depth=max_depth)
        else:
            value = {"_uint": int.from_bytes(val, "little"), "_hex": val.hex()}
        key = str(num)
        if key in out:
            if not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key].append(value)
        else:
            out[key] = value
    return out


def is_leaf(node):
    """decode 把 fixed 与解析不出的 bytes 表示为带 _hex 的字典，到此处不再继续展开"""
    return isinstance(node, dict) and "_hex" in node


def cell(value):
    if value is None:
        return ""
    if is_leaf(value):
        # fixed 给出数值，其余 bytes 原样给出 hex
        return str(value["_uint"]) if "_uint" in value else f"(hex:{value['_hex']})"
    return str(value)


def format_timestamp(value, fmt):
    """整数时间戳按秒/毫秒自动判定并格式化；不适用返回 None"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    for seconds, microsecond in ((value, 0), (value // 1000, (value % 1000) * 1000)):
        try:
            moment = datetime.fromtimestamp(seconds).replace(microsecond=microsecond)
        except (OverflowError, OSError, ValueError):
            continue
        if 2000 <= moment.year <= 2100:
            return moment.strftime(fmt)
    return None


def timestamp_units(value):
    """整数时间戳可用的单位集合，只保留 2000 到 2100 年"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return set()
    units = set()
    for unit, seconds in (("s", value), ("ms", value // 1000)):
        try:
            moment = datetime.fromtimestamp(seconds)
        except (OverflowError, OSError, ValueError):
            continue
        if 2000 <= moment.year <= 2100:
            units.add(unit)
    return units


def is_message(decoded):
    """解出的值是消息时才算能出子表；文本与解析不出的字节都不是"""
    return isinstance(decoded, dict) and not is_leaf(decoded)


def blob_kind(blob, max_depth):
    return "protobuf" if is_message(decode(blob, max_depth=max_depth)) else "blob"


def blob_cell(blob, limit, max_depth):
    """BLOB 的显示文本；空值单独标记，超过上限时省略 hex；limit 为负表示不限"""
    if not blob:
        return "(empty)"
    kind = blob_kind(blob, max_depth)
    if limit < 0 or len(blob) <= limit:
        return f"({kind}:hex:{blob.hex()})"
    return f"({kind})"


def json_value(value):
    """按 values 的规则表示一个值：NULL 为 null，其余为 JSON 字符串"""
    return json.dumps(None if value is None else str(value), ensure_ascii=False)


def value_text(value, column, time_columns, time_format, short_blob, max_depth):
    """普通表格单元格：NULL 为 null，BLOB 按显示上限表示，时间列可格式化"""
    if isinstance(value, bytes):
        return blob_cell(value, short_blob, max_depth)
    text = "null" if value is None else cell(value)
    if time_format and column in time_columns and value is not None:
        stamp = format_timestamp(value, time_format)
        if stamp:
            text = stamp
    return text


def value_json(value, column, time_columns, time_format, short_blob, max_depth):
    """values/附加信息单元格：在 value_text 的规则上再做 JSON 标量编码"""
    if isinstance(value, bytes):
        return json_value(blob_cell(value, short_blob, max_depth))
    if time_format and column in time_columns:
        stamp = format_timestamp(value, time_format)
        if stamp:
            return json_value(stamp)
    return json_value(value)
