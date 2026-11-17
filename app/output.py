"""记录序列的 JSON 输出。"""

import json
import sys
from collections.abc import Iterable, Mapping

__all__ = ["render_json"]


def render_json(records: Iterable[Mapping[str, object]] | Mapping[str, object] | None, file=None) -> None:
    """把记录序列、单个记录或 None 写成 JSON；file 缺省为 stdout。

    记录中的 NamedTuple 按字段名写成对象，嵌套的同样处理；否则 json 会把它们当成数组。
    """
    if file is None:
        file = sys.stdout
    data = records if records is None or isinstance(records, Mapping) else list(records)
    json.dump(_plain(data), file, ensure_ascii=False, indent=2)
    print(file=file)


def _plain(value: object) -> object:
    """把记录中的 NamedTuple 递归转换为字典，其余类型原样返回"""
    if isinstance(value, tuple) and hasattr(value, "_asdict"):
        return {name: _plain(item) for name, item in value._asdict().items()}
    if isinstance(value, Mapping):
        return {name: _plain(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
