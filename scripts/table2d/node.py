"""json 风格使用的 blob 节点：{len, hex, decoded}，以及按字段路径遍历、裁剪节点。"""

from lib.wire import as_text, parse_fields

# 解成节点时的下钻上限
_MAX_NODE_DEPTH = 12


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
