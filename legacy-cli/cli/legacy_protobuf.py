"""Legacy 的 protobuf 转换规则；不读取数据库或执行输出。"""

from lib.wire import as_text, parse_fields

__all__ = ["decode_classic_groups", "decode_classic_message", "decode_c2c"]

_MAX_DEPTH = 32
_CONTAINERS = {
    "groups": {25011: "leaf"},
    "message": {40800: "segment"},
    "segment": {47423: "segment", 48403: "leaf"},
    "leaf": {},
}


def _append_field(out: dict, num: int, value: object) -> None:
    key = str(num)
    if key not in out:
        out[key] = value
    elif isinstance(out[key], list):
        out[key].append(value)
    else:
        out[key] = [out[key], value]


def _scalar(kind: str, raw: int | bytes) -> int | bytes:
    if kind in ("fixed32", "fixed64"):
        return int.from_bytes(raw, "little")
    return raw


def _decode_classic(data: bytes, context: str, depth: int) -> dict:
    if depth >= _MAX_DEPTH:
        raise ValueError("protobuf 嵌套超过 32 层")
    fields = parse_fields(data)
    if fields is None:
        raise ValueError("protobuf 线格式无效")
    containers = _CONTAINERS[context]
    out = {}
    for num, kind, raw in fields:
        if num in containers:
            if kind != "bytes":
                raise ValueError(f"protobuf 容器 {num} 不是 bytes")
            value = _decode_classic(raw, containers[num], depth + 1)
        else:
            value = _scalar(kind, raw)
        _append_field(out, num, value)
    return out


def decode_classic_groups(data: bytes) -> dict:
    """返回数字字符串键的分组树，名称保留 bytes，重复字段为列表。

    仅展开 25011 容器；线格式、容器类型错误或嵌套达到 32 层抛 ValueError。
    """
    return _decode_classic(data, "groups", 0)


def decode_classic_message(data: bytes) -> dict:
    """返回经典导出器的消息树，文本和未知 bytes 保留原值。

    仅展开消息段、引用原文及红包容器；重复字段为列表。
    根深度为 0，深度达到 32、线格式或容器类型错误时抛 ValueError。
    """
    return _decode_classic(data, "message", 0)


def _decode_c2c(data: bytes, depth: int) -> dict | bytes:
    if not data or depth >= _MAX_DEPTH:
        return data
    fields = parse_fields(data)
    if fields is None:
        return data
    out = {}
    for num, kind, raw in fields:
        if kind == "bytes" and as_text(raw) is None:
            value = _decode_c2c(raw, depth + 1)
        else:
            value = _scalar(kind, raw)
        _append_field(out, num, value)
    return out


def decode_c2c(data: object) -> object:
    """返回启发式消息树；非 bytes/bytearray 输入原样返回。

    根直接解析，嵌套 bytes 优先保留可打印 UTF-8 文本，否则尝试解析。
    空值、解析失败或深度达到 32 时保留 bytes；重复字段为列表，整数无符号。
    """
    if not isinstance(data, (bytes, bytearray)):
        return data
    return _decode_c2c(bytes(data), 0)
