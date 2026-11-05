"""以 JSON 渲染 Sheet。"""

import json
from collections.abc import Sequence

from rich.console import Console
from rich.text import Text

from render.sheet import Column, Sheet, StyledRow, cell_style, styled_rows

__all__ = ["render_json"]


def _object(columns: Sequence[Column], row: StyledRow, *, comment: bool) -> Text:
    """不带注释时逐字等同 json.dumps(record, indent=2) 再整体缩进 2 格；手工拼接是为了按列着色并单独给 null 附加 bright_black。"""
    text = Text("  {", style=row.style or "")
    if comment and row.row_id is not None:
        text.append(f" // rowid: {row.row_id}", style="dim")
    text.append("\n")
    for index, (column, cell) in enumerate(zip(columns, row.cells, strict=True)):
        value = ("null", "bright_black") if cell is None else json.dumps(cell, ensure_ascii=False)
        pair = Text.assemble(f"{json.dumps(column.title, ensure_ascii=False)}: ", value, style=cell_style(column, row.style))
        comma = "," if index < len(columns) - 1 else ""
        text.append_text(Text.assemble("    ", pair, f"{comma}\n"))
    text.append("  }")
    return text


def render_json(sheet: Sheet) -> None:
    """把 sheet 以对象数组输出到 stdout，每行一个对象，键为列标题。

    None 输出为 bright_black 的 null，中文原样输出；每个对象从 { 到 } 整体使用该行的 row_styles，对象间的逗号与 [ ] 不着色。
    每个 "键": 值 使用列样式与行样式的叠加，行尾逗号不使用列样式。
    row_ids 不写入对象；stdout 是终端时以 dim 的 // rowid: N 注释附在 { 之后，不使用行样式。
    忽略 title，非 TTY 时不输出样式与注释，输出与整体 json.dumps(indent=2) 逐字一致。
    row_styles 或 row_ids 与 rows 数量不一致时抛 ValueError。
    """
    console = Console(soft_wrap=True, markup=False, emoji=False, highlight=False)
    blocks = [_object(sheet.columns, row, comment=console.is_terminal) for row in styled_rows(sheet)]
    if not blocks:
        console.print("[]")
        return
    console.print("[")
    for index, block in enumerate(blocks):
        console.print(block, end="")
        console.print("," if index < len(blocks) - 1 else "")
    console.print("]")
