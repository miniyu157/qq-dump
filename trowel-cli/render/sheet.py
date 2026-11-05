"""各渲染函数共用的二维数据结构，不依赖 rich。"""

from collections.abc import Iterator, Sequence
from itertools import repeat
from typing import Literal, NamedTuple

__all__ = ["Cell", "Column", "Sheet", "StyledRow", "cell_style", "styled_rows"]

Cell = str | int | float | None


class Column(NamedTuple):
    """一列的标题；align 只用于表格，决定该列单元格的水平对齐。

    null_text 为 None 在表格与 kv 中的显示文字，json 不读，None 一律输出 null。
    style 为该列的 rich 样式串，与行样式叠加的规则见 cell_style。
    """

    title: str
    align: Literal["left", "right"] = "left"
    null_text: str = "NULL"
    style: str | None = None


class Sheet(NamedTuple):
    """rows 的每行单元格与 columns 一一对应。

    title 只用于表格；row_styles 为逐行的 rich 样式串，None 表示不附加样式。
    row_ids 为逐行的 rowid，不属于 columns；表格显示为首列 #，kv 与 json 显示为每组的标记。
    """

    columns: Sequence[Column]
    rows: Sequence[Sequence[Cell]]
    title: str | None = None
    row_styles: Sequence[str | None] | None = None
    row_ids: Sequence[int] | None = None


class StyledRow(NamedTuple):
    cells: Sequence[Cell]
    style: str | None
    row_id: int | None


def styled_rows(sheet: Sheet) -> Iterator[StyledRow]:
    """逐行给出单元格、样式与 rowid；row_styles 或 row_ids 与 rows 数量不一致时抛 ValueError。"""
    count = len(sheet.rows)
    styles = repeat(None, count) if sheet.row_styles is None else sheet.row_styles
    ids = repeat(None, count) if sheet.row_ids is None else sheet.row_ids
    return (StyledRow(*item) for item in zip(sheet.rows, styles, ids, strict=True))


def cell_style(column: Column, row_style: str | None) -> str:
    """列样式在下、行样式在上叠加：属性合并，前景色冲突时以行样式为准，与 rich 表格的规则一致。"""
    return " ".join(style for style in (column.style, row_style) if style)
