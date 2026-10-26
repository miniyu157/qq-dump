"""protobuf 线格式的最小解析：只切分字段，不解释语义"""

from typing import Literal, NamedTuple

__all__ = ["Field", "as_text", "parse_fields"]


class Field(NamedTuple):
    """线格式字段：字段号、线型类别与原始值。"""

    num: int
    kind: Literal["varint", "fixed64", "bytes", "fixed32"]
    value: int | bytes


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """读取一个 varint，返回 (值, 新下标)；超过 10 字节时抛 ValueError。"""
    result = shift = 0
    while True:
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint 过长")


def parse_fields(buf: bytes) -> list[Field] | None:
    """按线格式扫描整段，成功返回 Field 列表；不支持的线型或截断返回 None。"""
    fields: list[Field] = []
    i, n = 0, len(buf)
    while i < n:
        try:
            key, i = _read_varint(buf, i)
        except (IndexError, ValueError):
            return None
        num, wire_type = key >> 3, key & 7
        if num == 0:
            return None
        if wire_type == 0:
            try:
                val, i = _read_varint(buf, i)
            except (IndexError, ValueError):
                return None
            fields.append(Field(num, "varint", val))
        elif wire_type == 1:
            if i + 8 > n:
                return None
            fields.append(Field(num, "fixed64", buf[i : i + 8]))
            i += 8
        elif wire_type == 2:
            try:
                ln, i = _read_varint(buf, i)
            except (IndexError, ValueError):
                return None
            if i + ln > n:
                return None
            fields.append(Field(num, "bytes", buf[i : i + ln]))
            i += ln
        elif wire_type == 5:
            if i + 4 > n:
                return None
            fields.append(Field(num, "fixed32", buf[i : i + 4]))
            i += 4
        else:
            return None
    return fields


def as_text(buf: bytes) -> str | None:
    """UTF-8 可解码且只含可打印字符或 \n\r\t 时返回文本，否则 None。"""
    if not buf:
        return None
    try:
        text = buf.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if all(c.isprintable() or c in "\n\r\t" for c in text) else None
