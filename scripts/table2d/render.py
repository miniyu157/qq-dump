"""二维表、kv 与 JSON 的 rich 渲染。"""

import json
import sys
from typing import NamedTuple

from rich.cells import cell_len
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from node import child_path

# 无终端时的分割线宽度
FALLBACK_WIDTH = 80


class Tip(NamedTuple):
    """某档原因的说法与两个范围的恢复开关"""

    noun: str
    column: str
    field: str


# Status 的成员名 -> Tip
TIPS = {
    "UNDEFINED": Tip("未定义", "-Cu, --show-undefined-columns", "-Pu, --show-undefined-fields"),
    "HIDDEN": Tip("已隐藏", "-Ch, --show-hidden-columns", "-Ph, --show-hidden-fields"),
    "DISCARDED": Tip("已丢弃", "-Cd, --show-discarded-columns", "-Pd, --show-discarded-fields"),
}


def line_width(text):
    """取最长一行的显示宽度，表头可能是两行"""
    return max(cell_len(line) for line in text.split("\n"))


def content_width(headers, grid):
    """按单元格内容累加所需宽度：每格左右各 1 空格，竖线比列数多 1"""
    widths = [max([line_width(headers[i])] + [cell_len(row[i]) for row in grid]) for i in range(len(headers))]
    return sum(w + 2 for w in widths) + len(widths) + 1


def header_lines(names, types, labels, prefix=""):
    """每列的表头按 列名、线格式类型、语义名称 逐行拼装；在所有列上都为空的那一行不出现"""
    rows = [[name.removeprefix(prefix)] for name in names]
    if any(name in types for name in names):
        for row, name in zip(rows, names):
            row.append(types.get(name, ""))
    if any(name in labels for name in names):
        for row, name in zip(rows, names):
            row.append(labels.get(name, ""))
    return ["\n".join(row) for row in rows]


def render_table(title, rows, names, types, labels, prefix=""):
    """title 由调用方给全，逐行原样打印在表格上方；prefix 是展开表里要移除的所属列前缀，只影响表头显示"""
    headers = header_lines(names, types, labels, prefix)
    grid = [[row.get(name, "") for name in names] for row in rows]
    out = Table()
    for header in headers:
        out.add_column(header, no_wrap=True)
    for row in grid:
        out.add_row(*row)
    # 固定按内容宽度渲染，不受终端约束，超出部分由终端折行；rich 自带的测量在列多时会塌缩，print(width=) 也不生效
    # highlight 一律关掉：rich 默认会给字符串里的数字与链接自动着色
    console = Console(width=max(content_width(headers, grid), line_width(title)), highlight=False)
    # 不走 Table 的 title，rich 会把标题折行到表格自身宽度内，长行会被切断
    print(titled(title))
    console.print(out)


def render_rule():
    """表格之间的分割线，宽度取终端；无终端时用固定值"""
    terminal = Console(highlight=False)
    Console(width=terminal.width if terminal.is_terminal else FALLBACK_WIDTH, highlight=False).print(Rule(style="dim"))


def render_progress(cache, table, index, total):
    """缓存阶段的进度提示，走标准错误，避免混进标准输出的表格；table 为 None 时提示缓存位置"""
    console = Console(stderr=True, highlight=False)
    if table is None:
        console.print(f"正在缓存 Protobuf 字段信息到 .cache/{cache.name}")
    else:
        console.print(f"  ({index}/{total}) 扫描 {table} 表...")


def render_reasons(console, reasons, scope):
    """逐条列出未渲染的原因，并给出恢复它的开关；scope 取 column 或 field"""
    for name, tip in TIPS.items():
        if reasons.get(name):
            console.print(f"  {reasons[name]} 个{tip.noun} (使用 {getattr(tip, scope)} 重新显示)")


def render_summary(columns, fields):
    """渲染前的收录说明：未渲染的列与 protobuf 字段按原因分列"""
    if not columns and not fields:
        return
    console = Console(stderr=True, highlight=False, style="dim")
    for noun, reasons, scope in (("列", columns, "column"), ("Protobuf 字段", fields, "field")):
        if not reasons:
            continue
        console.print(f"{sum(reasons.values())} {noun}未渲染，其中")
        render_reasons(console, reasons, scope)
        console.print()


def render_count(count):
    print(count)


STATUS_STYLES = {
    "UNDEFINED": "dim",
    "HIDDEN": "yellow",
    "DISCARDED": "red",
    "EXPLORING": "magenta",
}


def status_row_styles(statuses):
    return [STATUS_STYLES.get(status) for status in statuses]


def render_small_table(rows, names, justify=(), row_styles=(), header_style="bold"):
    """小表按终端宽度渲染，不输出制表线；row_styles 为逐行 rich 样式"""
    aligns = list(justify)
    out = Table(box=None, padding=(0, 2), header_style=header_style)
    for index, name in enumerate(names):
        align = aligns[index] if index < len(aligns) else "left"
        header = Text.from_ansi(name) if isinstance(name, str) else name
        out.add_column(header, justify=align)
    for index, row in enumerate(rows):
        style = row_styles[index] if index < len(row_styles) else None
        cells = [Text.from_ansi(cell) if isinstance(cell, str) else cell for cell in row]
        out.add_row(*cells, style=style)
    Console().print(out)


def join_values(values, invert_empty=True):
    """用逗号加空格连接展示值；终端里值按位置轮换颜色、逗号 faint，管道下保持纯文本"""
    colored = sys.stdout.isatty()
    parts = []
    for index, value in enumerate(values):
        if colored:
            style = VALUE_COLORS[index % len(VALUE_COLORS)]
            if invert_empty and value in ("null", '""'):
                style += ";7"
            value = marked(value, style)
        parts.append(value)
    separator = marked(",", FAINT) if colored else ","
    return f"{separator} ".join(parts)


def render_values(entries):
    """逐行输出 (显示值, 次数)；次数始终显示"""
    colored = sys.stdout.isatty()
    for values, count in entries:
        prefix = marked(f"{count} x", FAINT if colored else "")
        print(f"{prefix} {join_values(values)}")


def quoted(value):
    """按 JSON 规则表示一个标量，中文保留原样"""
    return json.dumps(value, ensure_ascii=False)


# JSON 里两种标注用的 ANSI 样式码：结构键淡显加反显
FAINT_INVERT = "2;7"

# 淡显的样式码，用于 kv 分隔线、values 计数前缀与结构逗号
FAINT = "2"

# values 与附加信息中按位置轮换的值颜色
VALUE_COLORS = ("32", "33", "34", "35", "36")

# 表前注释的样式码
TITLE = "36"

# 字段按 maps 的状态着色：未定义淡显，已隐藏标黄，已丢弃标红，探索中标紫；已映射的不着色
COLORS = {
    "UNDEFINED": "2",
    "HIDDEN": "33",
    "DISCARDED": "31",
    "EXPLORING": "35",
}


def marked(text, code):
    """按需给一段文本附加 ANSI 样式码，code 为空时不加"""
    return f"\x1b[{code}m{text}\x1b[0m" if code else text


def faint(text):
    """终端里淡显，管道下保持纯文本"""
    return marked(text, FAINT) if sys.stdout.isatty() else text


def underlined(text):
    """终端里加下划线，管道下保持纯文本"""
    return marked(text, "4") if sys.stdout.isatty() else text


def row_marker(number):
    """原始行号标记；终端里红色反显，管道下保持纯文本"""
    text = f"#{number}"
    return marked(text, "31;7") if sys.stdout.isatty() else text


def titled(text):
    """表前注释：写在终端上时给一层青色，重定向到文件时保持原样"""
    return marked(text, TITLE) if sys.stdout.isatty() else text


def json_lines(node, labels, states, dim, path="", depth=0, opener="{"):
    """节点写成 JSON 文本行，自成一对花括号；opener 由调用方给出首行，可以是 '键: {'"""
    pad = "  " * depth
    inner = f"{pad}  "
    code = FAINT_INVERT if dim else ""
    lines = [
        f"{pad}{opener}",
        f"{inner}{marked(quoted('len') + ': ' + quoted(node['len']), code)},",
    ]
    if "hex" in node:
        lines.append(f"{inner}{marked(quoted('hex') + ': ' + quoted(node['hex']), code)},")
    lines.append(f"{inner}{marked(quoted('decoded') + ': {', code)}")
    entries = list(node["decoded"].items())
    for position, (key, value) in enumerate(entries):
        lines += entry_lines(key, value, labels, states, dim, path, depth + 2, position < len(entries) - 1)
    lines.append(f"{inner}}}")
    lines.append(f"{pad}}}")
    return lines


def entry_lines(key, value, labels, states, dim, path, depth, comma, node_path=None):
    """一个字段写成 JSON 文本行；未定义的字段淡显。

    node_path 是值为节点时的路径根，缺省沿用本字段的路径。整表 JSON 的列键要另给根：
    blob 的内容从它自身起算，与列同号的最外层字段只是容器，跟着列名再叠一层会与映射表失配
    """
    name = child_path(path, key)
    label = labels.get(name)
    display = quoted(f"[{key}] {label}" if label else key)
    code = COLORS.get(states.get(name)) if dim else ""
    pad = "  " * depth
    root = name if node_path is None else node_path
    if isinstance(value, dict) and "decoded" in value:
        lines = json_lines(value, labels, states, dim, root, depth, marked(f"{display}: {{", code))
    elif isinstance(value, list):
        lines = [f"{pad}{marked(f'{display}: [', code)}"]
        for position, item in enumerate(value):
            tail = "," if position < len(value) - 1 else ""
            if isinstance(item, dict) and "decoded" in item:
                lines += json_lines(item, labels, states, dim, root, depth + 1)
                lines[-1] = f"{pad}  }}{tail}"
            else:
                lines.append(f"{pad}  {quoted(item)}{tail}")
        lines.append(f"{pad}]")
    else:
        lines = [f"{pad}{marked(f'{display}: {quoted(value)}', code)}"]
    if comma:
        lines[-1] += ","
    return lines


def json_row_lines(row, names, labels, states, dim):
    """一个行对象写成 JSON 文本行，列项交给 entry_lines；列的值为 blob 节点时其内容自成一体"""
    lines = ["  {"]
    for position, name in enumerate(names):
        lines += entry_lines(name, row[name], labels, states, dim, "", 2, position < len(names) - 1, node_path="")
    lines.append("  }")
    return lines


def render_json_table(rows, names, labels, states):
    """整表的 JSON 形态，标准输出里只有这一个文档。

    着色随终端与否：管道下不带 ANSI，因此是合法 JSON。文档用 print 写出而不经 rich，
    后者会按宽度折行，把长的 hex 撕开
    """
    dim = sys.stdout.isatty()
    lines = ["["]
    for position, row in enumerate(rows):
        lines += json_row_lines(row, names, labels, states, dim)
        if position < len(rows) - 1:
            lines[-1] += ","
    lines.append("]")
    print("\n".join(lines))


def kv_codes(state):
    """一行 kv 的样式码 (键, 值)：状态色取自 COLORS，加粗只用在键上；已映射的键只有加粗，值不着色"""
    tint = COLORS[state] if state else ""
    return (f"1;{tint}" if tint else "1", tint)


def render_kv(title, rows, names, labels, states, prefix=""):
    """键值块：行内的 # 值作块首行，其余按 列名 语义名称 逐行给出，键在块内按显示宽度补齐。
    终端里键按 maps 的状态着色并加粗、值只带状态色，块间的分隔线淡显
    """
    print(titled(title))
    colored = sys.stdout.isatty()
    keys = [name for name in names if name != "#"]
    texts = {}
    for name in keys:
        display = name.removeprefix(prefix)
        label = labels.get(name)
        texts[name] = f"{display} {label}" if label else display
    width = max((cell_len(text) for text in texts.values()), default=0)
    for position, row in enumerate(rows):
        if position:
            print(marked("---", FAINT if colored else ""))
        if "#" in row:
            print(f"# {row['#']}")
        for name in keys:
            text = texts[name]
            padded = text + " " * (width - cell_len(text))
            value = row.get(name, "")
            key_code, value_code = kv_codes(states.get(name)) if colored else ("", "")
            head = marked(f"{padded}:", key_code)
            print(f"{head} {marked(value, value_code)}" if value else head)


def render_rows(style, title, rows, names, types, labels, states, prefix=""):
    """按风格渲染一张表：kv 走键值块，json 走整表 JSON，其余走二维表。
    kv 与 json 都不看线格式类型层，二维表不看状态"""
    if style == "kv":
        render_kv(title, rows, names, labels, states, prefix)
    elif style == "json":
        render_json_table(rows, names, labels, states)
    else:
        render_table(title, rows, names, types, labels, prefix)


def row_style(count, defined, total):
    """0 行的表淡显；有定义但未满的标黄，已满的标绿，一列未定义的保持原样"""
    if count == 0:
        return "dim"
    if defined == 0:
        return None
    return "green" if defined == total else "yellow"


def render_tables(entries):
    """entries 每项为 (表名, 行数, (已定义列数, 列总数), (已定义字段数, 字段号种数))"""
    out = Table()
    out.add_column("表名")
    out.add_column("行数", justify="right")
    out.add_column("已定义列", justify="right")
    out.add_column("已定义字段", justify="right")
    for name, count, (defined, total), (fields, observed) in entries:
        field_text = f"{fields}/{observed} ({fields / observed:.0%})" if observed else f"{fields}/0"
        out.add_row(name, str(count), f"{defined}/{total} ({defined / total:.0%})", field_text, style=row_style(count, defined, total))
    Console().print(out)
