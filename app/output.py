"""记录序列的 JSON 输出。"""

import json
import sys
from collections.abc import Iterable, Mapping

__all__ = ["render_json"]


def render_json(records: Iterable[Mapping[str, object]] | Mapping[str, object] | None, file=None) -> None:
    """把记录序列、单个记录或 None 写成 JSON；file 缺省为 stdout。"""
    if file is None:
        file = sys.stdout
    data = records if records is None or isinstance(records, Mapping) else list(records)
    json.dump(data, file, ensure_ascii=False, indent=2)
    print(file=file)
