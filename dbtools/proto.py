"""Protobuf 黑盒解码。

公开 API:
    decode_proto_field(blob, column, target) -> list[target]
    decode_proto_struct(struct, data, target) -> target

两层职责：
- decode_proto_field:  QQNT 专用——解 outer repeated wrapper（Column.id 作 key），委托通用解码
- decode_proto_struct: 通用解码器——只认 ProtoStruct，递归处理 nested / enum / bytes 嵌套
"""

from __future__ import annotations

import warnings
from dataclasses import fields as dc_fields
from typing import TypeVar, get_args, get_origin, get_type_hints

import blackboxprotobuf

from .schema.base import Column, ProtoStruct

T = TypeVar("T")


def decode_proto_struct(struct: ProtoStruct, data: dict, target: type[T]) -> T:
    """将已解码的 protobuf dict 按 ProtoStruct 映射到 target dataclass。

    纯解码器——只看 ProtoStruct + ProtoField，不假设数据来源（SQL 列 / 文件 / 网络）。
    """
    proto_map = {str(pf.number): pf for pf in struct.fields}
    valid = {f.name for f in dc_fields(target)}
    hints = _safe_get_type_hints(target)

    kwargs: dict[str, object] = {}
    for key, raw_val in data.items():
        pf = proto_map.get(key)
        if pf is None or pf.name not in valid:
            continue
        if raw_val is None:
            continue
        kwargs[pf.name] = _coerce(pf, raw_val, hints)

    return target(**kwargs)


def decode_proto_field(blob: bytes, column: Column, target: type[T]) -> list[T]:
    """从 QQNT BLOB 列解码 protobuf 数组。

    QQNT 编码约定：外层 message 的 repeated 字段用 SQL 列号（Column.id）作 field number，
    每个 repeated 元素的内层结构由 Column.proto 描述。
    """
    if column.proto is None:
        return []

    decoded, _ = blackboxprotobuf.decode_message(blob)
    items = decoded.get(column.id)

    if items is None:
        return []
    if not isinstance(items, list):
        items = [items]

    return [decode_proto_struct(column.proto, item, target) for item in items]


# ═══════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════


def _coerce(pf, raw_val, hints: dict[str, type]):
    """按 ProtoField 类型规则矫形 raw_val，必要时递归解码嵌套结构。"""

    ptype = pf.field_type

    if ptype == "string":
        if isinstance(raw_val, bytes):
            return raw_val.decode("utf-8")
        return raw_val

    if ptype == "bytes":
        if pf.struct is not None and isinstance(raw_val, bytes):
            # opaque bytes 嵌套：bytes 字段内含序列化的 protobuf message
            inner, _ = blackboxprotobuf.decode_message(raw_val)
            return decode_proto_struct(pf.struct, inner, _nested_target(pf.name, hints))
        return raw_val

    if ptype == "nested":
        target_t = _nested_target(pf.name, hints)
        if pf.repeated and isinstance(raw_val, list):
            return [decode_proto_struct(pf.struct, item, target_t) for item in raw_val]
        return decode_proto_struct(pf.struct, raw_val, target_t)

    if ptype == "enum" and pf.enum is not None:
        for ev in pf.enum.values:
            if ev.number == raw_val:
                return ev.label
        return raw_val  # 未找到对应 label，保留原始 int

    # varint / 未知类型 → 直通
    return raw_val


def _nested_target(field_name: str, hints: dict[str, type]) -> type:
    """从 target type hints 解析嵌套字段的目标类型（unwrap Optional / list）。"""
    hinted = hints.get(field_name)
    if hinted is None:
        warnings.warn(f"field {field_name!r} has no type hint, keeping raw dict")
        return dict

    origin = get_origin(hinted)
    if origin is not None:
        args = get_args(hinted)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return non_none[0]

    return hinted


def _safe_get_type_hints(target: type) -> dict[str, type]:
    """安全获取 type hints；失败时 warning 并返回空 dict（后续降级为 raw dict）。"""
    try:
        return get_type_hints(target)
    except Exception as e:
        warnings.warn(f"get_type_hints() failed for {target.__name__}: {e}")
        return {}
