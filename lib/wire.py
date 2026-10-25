"""protobuf 线格式的最小解析：只切分字段，不解释语义"""

from typing import Literal, NamedTuple

__all__ = ["Field", "as_node", "as_text", "child_path", "node_paths", "parse_fields", "prune", "without_hex"]

# 解成节点时的下钻上限
_MAX_NODE_DEPTH = 12


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


def _as_decoded(buf: bytes, depth: int = 0) -> str | dict[str, object]:
    """解出嵌套结构：文本与标量原样，消息递归并整体化为 len/hex/decoded 节点，解析不出的给 _hex"""
    if not buf:
        return ""
    text = as_text(buf)
    if text is not None:
        return text
    if depth >= _MAX_NODE_DEPTH:
        return {"_hex": buf.hex()}
    fields = parse_fields(buf)
    if not fields:
        return {"_hex": buf.hex()}
    out: dict[str, object] = {}
    for num, kind, raw in fields:
        if kind == "varint":
            value: object = raw
        elif kind == "bytes":
            value = _as_decoded(raw, depth + 1)
            if isinstance(value, dict) and "_hex" not in value:
                value = {"len": len(raw), "hex": raw.hex(), "decoded": value}
        else:
            value = {"_uint": int.from_bytes(raw, "little"), "_hex": raw.hex()}
        key = str(num)
        if key in out:
            if not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key].append(value)
        else:
            out[key] = value
    return out


def as_node(blob: bytes) -> dict[str, object]:
    return {"len": len(blob), "hex": blob.hex(), "decoded": _as_decoded(blob)}


def child_path(path: str, key: str) -> str:
    return f"{path}.{key}" if path else str(key)


def node_paths(node: object, path: str = "") -> set[str]:
    """节点里出现的全部字段路径"""
    if isinstance(node, list):
        return {name for item in node for name in node_paths(item, path)}
    if not isinstance(node, dict) or "decoded" not in node:
        return set()
    names = set()
    for key, value in node["decoded"].items():
        name = child_path(path, key)
        names.add(name)
        names |= node_paths(value, name)
    return names


def without_hex(node: object) -> object:
    """递归只保留可解码节点的 len 与 decoded；无法解码的 _hex 节点原样返回"""
    if isinstance(node, list):
        return [without_hex(item) for item in node]
    if not isinstance(node, dict) or "decoded" not in node:
        return node
    return {"len": node["len"], "decoded": {key: without_hex(value) for key, value in node["decoded"].items()}}


def prune(node: object, hidden: set[str], path: str = "") -> object:
    """按给定的字段路径集合裁掉节点里的字段"""
    if isinstance(node, list):
        return [prune(item, hidden, path) for item in node]
    if not isinstance(node, dict) or "decoded" not in node:
        return node
    kept = {}
    for key, value in node["decoded"].items():
        name = child_path(path, key)
        if name not in hidden:
            kept[key] = prune(value, hidden, name)
    return {**node, "decoded": kept}
