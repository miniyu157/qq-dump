"""以键值对渲染 Sheet。"""

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from render.sheet import Sheet, cell_style, styled_rows

__all__ = ["render_kv"]


def render_kv(sheet: Sheet) -> None:
    """把 sheet 输出到 stdout，每行输出一组「列标题: 值」，组间以 dim 的 --- 分隔。

    键按显示宽度对齐并加粗，None 显示为 bright_black 的该列 null_text；每个「键: 值」使用列样式与行样式的叠加，--- 不随之着色。
    row_ids 存在时每组上方输出 cyan 加粗的 # N，不使用行样式。
    忽略 title，非 TTY 时不输出样式。row_styles 或 row_ids 与 rows 数量不一致时抛 ValueError。
    """
    console = Console(soft_wrap=True, markup=False, emoji=False, highlight=False)
    width = max((cell_len(column.title) for column in sheet.columns), default=0)
    keys = [column.title + " " * (width - cell_len(column.title)) for column in sheet.columns]
    for index, row in enumerate(styled_rows(sheet)):
        if index:
            console.print("---", style="dim")
        if row.row_id is not None:
            console.print(f"# {row.row_id}", style="bold cyan")
        for column, key, cell in zip(sheet.columns, keys, row.cells, strict=True):
            value = (column.null_text, "bright_black") if cell is None else str(cell)
            console.print(Text.assemble((key, "bold"), ": ", value, style=cell_style(column, row.style)))
