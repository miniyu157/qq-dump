"""count-by 统计表的渲染路径。"""

import re
import sys
from dataclasses import dataclass

from rich.cells import cell_len
from rich.console import Console
from rich.table import Table
from rich.text import Text
from value_format import value_json, value_text

from render import faint, join_values, marked, row_marker, underlined

# rich 的表头样式会连单元格内边距一起下划线, 颜色 span 的 reset 也会中断下划线;
# 因此渲染后只给表头行首末可见字符之间补连续下划线
ANSI_SGR = re.compile(r"\x1b\[[0-9;]*m")

# 统计表头起始行: 值(列名) [枚举] [父级数] 数量 占比; 附加信息列头过长时会被折行
STATS_HEADER_START = re.compile(r"^\s*值\([^)]*\)\s+(?:枚举\s+)?(?:父级数\s+)?数量\s+占比")

# 统计行首格的零宽层级标记; 重复次数减一即层级
LEVEL_MARKER = "​⁠"

# rich 单元格左右各留 2 格
CELL_SIDE_PADDING = 2

# 每层缩进 4 格; 层级竖线随之每层右移同样的距离
STAT_INDENT = "    "
GUIDE_STEP = len(STAT_INDENT)


@dataclass(frozen=True)
class ValueFormat:
    """count-by 值列与附加信息的显示格式"""

    time_columns: frozenset[str]
    time_format: str
    short_blob: int
    max_depth: int


def stat_info(records, display_columns, value_format, row_number):
    """一个分组的附加信息: 每行各展示列的值，按需前置原始行号"""
    lines = []
    for record in records:
        values = [value_json(record[column], column, value_format.time_columns, value_format.time_format, value_format.short_blob, value_format.max_depth) for column in display_columns]
        prefix = f"{row_marker(record['#'])} " if row_number else ""
        lines.append(prefix + join_values(values))
    return "\n".join(lines)


def render_count_by(entries, options, total, value_format, row_number):
    """--count-by 的渲染入口。"""
    if total == 0:
        return

    count_columns = options.columns
    display_columns = options.display_columns
    padding = options.padding
    guides = options.guides
    show_parents = options.parent_count
    info_header = f"附加信息({join_values(display_columns, invert_empty=False)})" if display_columns else ""
    value_headers = [f"值({column})" for column in count_columns]
    last = len(value_headers) - 1
    show_name = tree_has_names(entries)
    show_info = bool(info_header)

    names, justify = stats_layout(show_name, show_info, value_headers[0], info_header, show_parents)
    if show_info and last != 0:
        names[-1] = ""
    if show_parents:
        names[1 + (1 if show_name else 0)] = ""
    # rich 的表头按底部对齐; 标记放在最后一个列头, 保证出现在表头首行
    names[-1 if show_info else 0] = mark_cell(names[-1 if show_info else 0], 0)

    rows = []

    def emit(nodes, parent_count, level):
        for node in nodes:
            value = value_text(node.value, count_columns[level], value_format.time_columns, value_format.time_format, value_format.short_blob, value_format.max_depth)
            info = ""
            if display_columns and level == last:
                info = faint("…") if node.records is None else stat_info(node.records, display_columns, value_format, row_number)
            row = stats_row(value, node.name, node.count, parent_count, info, node.parents, show_name, show_info, show_parents, STAT_INDENT * level)
            rows.append(mark_row(row, level))
            if not node.children:
                continue
            header, _ = stats_layout(show_name, show_info, value_headers[level + 1], info_header, show_parents)
            if show_info and level + 1 != last:
                header[-1] = ""
            # 子层列头在表体内，需显式加粗；首格承担缩进
            header_row = [header_cell(STAT_INDENT * (level + 1) + header[0]), *[header_cell(cell) for cell in header[1:]]]
            rows.append(mark_row(header_row, level + 1))
            emit(node.children, node.count, level + 1)
            label = Text(STAT_INDENT * (level + 1))
            label.append(f"样本数量: {node.count}, 取值: {len(node.children)} 种", style="underline")
            rows.append(mark_row([label, *([""] * (len(names) - 1))], level + 1))

    emit(entries, total, 0)
    render_tree_table(rows, names, justify, padding, guides)
    print(underlined(f"样本数量: {total}, 取值: {len(entries)} 种"))


def tree_has_names(entries):
    for entry in entries:
        if entry.name or tree_has_names(entry.children):
            return True
    return False


def stats_layout(show_name, show_info, value_header, info_header, show_parents=False):
    """统计树某一层的列名与对齐；各层共用"""
    names = [value_header, *(["枚举"] if show_name else []), *(["父级数"] if show_parents else []), "数量", "占比"]
    justify = ["left", *(["left"] if show_name else []), *(["right"] if show_parents else []), "right", "right"]
    if show_info:
        names.append(info_header)
        justify.append("left")
    return names, justify


def stats_row(value, name, count, total, info, parents, show_name, show_info, show_parents, prefix=""):
    """统计树的一行；prefix 是该层的缩进"""
    row = [prefix + value]
    if show_name:
        row.append(name or "")
    if show_parents:
        if parents is None:
            row.append("")
        else:
            text = str(parents)
            if parents > 1 and sys.stdout.isatty():
                text = marked(text, "31")
            row.append(text)
    row += [str(count), f"{count / total:.2%}"]
    if show_info:
        row.append(info)
    return row


def mark_cell(value, level):
    """首格前置零宽层级标记; 文本样式保持不变"""
    marker = LEVEL_MARKER * (level + 1)
    if isinstance(value, Text):
        text = Text(marker)
        text.append(value)
        return text
    return marker + value


def mark_row(row, level):
    """标记统计行的层级, 供渲染后识别新行与续行"""
    return [mark_cell(row[0], level), *row[1:]]


def header_cell(value):
    """子层表头单元格：先解析 ANSI 颜色，再整体加粗，避免颜色码被当作可见字符测量"""
    text = Text.from_ansi(value)
    text.stylize("bold")
    return text


def table_width(names, rows, padding):
    """表格不折行所需的内容宽度：各列最长行的显示宽度，加左右内边距"""
    widths = []
    for index, name in enumerate(names):
        header = Text.from_ansi(name) if isinstance(name, str) else name
        width = max((cell_len(line) for line in header.plain.split("\n")), default=0)
        for row in rows:
            cell = row[index] if index < len(row) else ""
            text = Text.from_ansi(cell) if isinstance(cell, str) else cell
            width = max(width, max((cell_len(line) for line in text.plain.split("\n")), default=0))
        widths.append(width)
    # 留 1 列余量，避免 rich 的边界舍入再次折行
    return sum(width + 2 * padding for width in widths) + 1


def render_tree_table(rows, names, justify, padding, guides):
    """统计树的小表：最左侧固定为 0，首列按最宽内容定宽，渲染后按需插入层级竖线与表头下划线。"""
    aligns = list(justify)
    table = Table(box=None, padding=(0, padding), header_style="bold")

    first_width = 0
    for value in [names[0], *(row[0] for row in rows)]:
        text = Text.from_ansi(value) if isinstance(value, str) else value
        first_width = max(first_width, max(cell_len(line) for line in text.plain.split("\n")))

    for index, name in enumerate(names):
        align = aligns[index] if index < len(aligns) else "left"
        header = Text.from_ansi(name) if isinstance(name, str) else name
        table.add_column(header, justify=align, min_width=first_width if index == 0 else None)

    for row in rows:
        cells = [Text.from_ansi(cell) if isinstance(cell, str) else cell for cell in row]
        table.add_row(*cells)

    # 管道输出没有终端宽度，按内容宽度渲染，避免 rich 以 80 列折行
    console = Console() if sys.stdout.isatty() else Console(width=table_width(names, rows, padding))
    with console.capture() as capture:
        console.print(table)
    text = apply_level_guides(capture.get(), guides, padding)
    sys.stdout.write(strip_left_padding(text, padding))


def apply_level_guides(text, guides, padding):
    """剥离层级标记并按需插入竖线; 只替换空白, 文字占据的位置保留文字。
    终端里先给表头加连续下划线"""
    lines = text.split("\n")
    current = None
    stripped = []
    levels = []
    for line in lines:
        count = line.count(LEVEL_MARKER)
        if count:
            current = count - 1
            line = line.replace(LEVEL_MARKER, "")
        stripped.append(line)
        levels.append(current)

    joined = "\n".join(stripped)
    if sys.stdout.isatty():
        joined = underline_header_lines(joined)
    if not guides:
        return joined
    rendered = joined.split("\n")
    out = []
    for level, line in zip(levels, rendered):
        if level is None:
            out.append(line)
            continue
        out.append(insert_guides(line, [padding + GUIDE_STEP * index for index in range(level + 1)]))
    return "\n".join(out)


def strip_left_padding(text, count):
    """移除表格左侧最外层的 count 个空格; ANSI 与列内缩进保持不变"""
    if not count:
        return text
    return "\n".join(strip_line_padding(line, count) for line in text.split("\n"))


def strip_line_padding(line, count):
    """按显示字符移除行首 count 个空格; 遇到首个非空格后停止, ANSI 序列保留"""
    removed = 0
    started = False
    out = []
    position = 0

    def consume(text):
        nonlocal removed, started
        for char in text:
            if not started and removed < count and char == " ":
                removed += 1
                continue
            started = True
            out.append(char)

    for match in ANSI_SGR.finditer(line):
        consume(line[position:match.start()])
        out.append(match.group())
        position = match.end()
    consume(line[position:])
    return "".join(out)


def underline_header_lines(text):
    """统计表头行加连续下划线；附加信息列头折行时整块处理, 其它行原样保留"""
    lines = text.split("\n")
    in_block = False
    balance = 0
    for index, line in enumerate(lines):
        plain = ANSI_SGR.sub("", line)
        if not in_block:
            if not STATS_HEADER_START.match(plain):
                continue
            info_start = plain.find("附加信息(")
            in_block = info_start >= 0
            balance = plain[info_start:].count("(") - plain[info_start:].count(")") if in_block else 0
            lines[index] = underline_span(line)
            if balance <= 0:
                in_block = False
            continue
        lines[index] = underline_span(line)
        balance += plain.count("(") - plain.count(")")
        if balance <= 0:
            in_block = False
    return "\n".join(lines)


def underline_span(line):
    """给一行中第一个到最后一个可见字符之间加连续下划线；ANSI 序列不占位置"""
    tokens = []
    position = 0
    for match in ANSI_SGR.finditer(line):
        tokens.extend(line[position:match.start()])
        tokens.append(match.group())
        position = match.end()
    tokens.extend(line[position:])

    visible = [index for index, token in enumerate(tokens) if not token.startswith("\x1b[") and not token.isspace()]
    if not visible:
        return line
    first, last = visible[0], visible[-1]
    out = tokens[:first]
    out.append("\x1b[1;4m")
    for index in range(first, last + 1):
        token = tokens[index]
        out.append(token)
        if index < last and token in ("\x1b[0m", "\x1b[m", "\x1b[24m"):
            out.append("\x1b[1;4m")
    out.append("\x1b[24m")
    out.extend(tokens[last + 1:])
    return "".join(out)


def insert_guides(line, columns):
    """在指定显示列把空白替换为竖线; 不覆盖文字, ANSI 序列不占列"""
    targets = sorted(set(columns))
    if not targets:
        return line
    tokens = []
    position = 0
    for match in ANSI_SGR.finditer(line):
        tokens.extend(line[position:match.start()])
        tokens.append(match.group())
        position = match.end()
    tokens.extend(line[position:])

    bar = faint("│")
    out = []
    column = 0
    target = 0
    for token in tokens:
        if token.startswith("\x1b["):
            out.append(token)
            continue
        while target < len(targets) and targets[target] < column:
            target += 1
        if target < len(targets) and targets[target] == column:
            out.append(bar if token == " " else token)
            target += 1
        else:
            out.append(token)
        column += cell_len(token)
    return "".join(out)
