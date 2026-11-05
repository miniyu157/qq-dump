"""以 rich 表格渲染 Sheet。"""

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from render.sheet import Sheet, styled_rows

__all__ = ["render_2d"]

_UNLIMITED_WIDTH = 1_000_000


def render_2d(sheet: Sheet) -> None:
    """把 sheet 输出到 stdout，None 显示为 bright_black 的该列 null_text。

    stdout 是终端时按终端宽度折行；否则不限宽度、不折行，且不输出颜色与样式。
    列样式作用于整列与表头，行样式叠加其上。row_ids 存在时显示为首列 #。
    row_styles 或 row_ids 与 rows 数量不一致时抛 ValueError。
    """
    table = Table(box=box.SIMPLE_HEAD, title=sheet.title)
    if sheet.row_ids is not None:
        table.add_column("#")
    for column in sheet.columns:
        table.add_column(column.title, justify=column.align, style=column.style, header_style=column.style)
    for row in styled_rows(sheet):
        cells = [Text(column.null_text, style="bright_black") if cell is None else Text(str(cell)) for column, cell in zip(sheet.columns, row.cells, strict=True)]
        if row.row_id is not None:
            cells.insert(0, Text(str(row.row_id)))
        table.add_row(*cells, style=row.style)
    console = Console()
    # 非 TTY 时 rich 默认按 80 列折行；表格不扩展，实际宽度只取内容所需
    if not console.is_terminal:
        console.width = _UNLIMITED_WIDTH
    console.print(table)
