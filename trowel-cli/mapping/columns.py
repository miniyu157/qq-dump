"""列在 maps/ 中登记的语义名称与状态。"""

from pathlib import Path
from typing import NamedTuple

from maps import Status
from maps.databases import for_file

__all__ = ["ColumnMapping", "column_mappings", "mapping_of"]


class ColumnMapping(NamedTuple):
    """label 为语义名称，未命名时为 None；status 为登记的状态，已登记但未设置时为 None。"""

    label: str | None
    status: Status | None


_UNDEFINED = ColumnMapping(None, Status.UNDEFINED)


def column_mappings(db_path: Path, table: str) -> dict[str, ColumnMapping]:
    """表在 maps/ 中登记的列，按列名索引；按库文件名与表名查找，未收录的表返回空字典。"""
    table_map = for_file(db_path, table)
    if table_map is None:
        return {}
    return {name: ColumnMapping(column.name, column.status) for name, column in table_map.columns.items()}


def mapping_of(mappings: dict[str, ColumnMapping], name: str) -> ColumnMapping:
    """取 column_mappings 结果中的一列；未登记的列视为 UNDEFINED。"""
    return mappings.get(name, _UNDEFINED)
