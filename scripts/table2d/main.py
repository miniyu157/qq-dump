#!/usr/bin/env python3
"""把 NT 数据库的表渲染成二维表格或 JSON。

二维表里主表一行对应数据库一行，blob 列在原位置显示为 (hash:摘要前七位)，用于定位下方的展开表。
每个 blob 另生成一张展开表，只解析一层：blob 自身的字段为列，其中仍是消息的字段
不再继续展开，原样输出 (hex:完整hex)。
表头按 列名、线格式类型、语义名称 逐行给出，整列为空的层不出现。

json 风格把整张表转换为一个文档，blob 就地内嵌，因此没有展开表，也没有摘要与行数这类引用。
"""

import argparse
import hashlib
import random
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime

import scan
from count_by import ValueFormat, build_entries, render_count_by, resolve_options, validate_columns
from value_format import cell, decode, format_timestamp, is_leaf, is_message, timestamp_units, value_json

from node import as_node, node_paths, prune, without_hex
from render import join_values, render_count, render_progress, render_rows, render_rule, render_small_table, render_summary, render_tables, render_values, row_marker, status_row_styles

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")

# 查询自己生成的列：原表次序序号、输入次序序号、限定集序号，都不属于表，取表头时排除
COMPUTED_COLUMNS = {"#", "o#", "s#"}

# 未给 --time-format 时使用的本地时间格式
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 自动时间列的每列取样上限与最少样本数
TIME_SAMPLE = 100
TIME_MIN_SAMPLES = 5


def detect_time_columns(conn, table):
    """按 rowid 取样，推断每个顶层非 blob 列是否为单一单位的时间戳列"""
    columns = [name for name, kind in conn.execute("SELECT name, type FROM pragma_table_info(?)", (table,)) if "BLOB" not in (kind or "").upper()]
    # 不按列名或语义名排除候选列：标识符与时间戳在数值上无法可靠区分，误判由显式 --time-columns 修正
    found = set()
    for column in columns:
        rows = conn.execute(f"SELECT [{column}] FROM [{table}] WHERE [{column}] IS NOT NULL AND [{column}] != 0 LIMIT ?", (TIME_SAMPLE,)).fetchall()
        values = [row[0] for row in rows]
        if len(values) < TIME_MIN_SAMPLES:
            continue
        units = None
        for value in values:
            value_units = timestamp_units(value)
            if not value_units:
                units = set()
                break
            units = value_units if units is None else units & value_units
            if not units:
                break
        if units is not None and len(units) == 1:
            found.add(column)
    return found


def labeled(value, path, table_map, time_columns=(), time_format=None):
    """按映射给值附加枚举名称；指定列且可转换时替换为格式化时间"""
    text = cell(value)
    if time_format and path in time_columns:
        stamp = format_timestamp(value, time_format)
        if stamp:
            text = stamp
    if table_map:
        name = table_map.enum(path, value)
        if name:
            text += f" ({name})"
    return text


def field_type(value):
    """从解码结果反推线格式类型"""
    if isinstance(value, (bool, int)):
        return "varint"
    if isinstance(value, str):
        return "string"
    if is_leaf(value):
        if "_uint" not in value:
            return "bytes"
        return "fixed32" if len(value["_hex"]) == 8 else "fixed64"
    if isinstance(value, dict):
        return "message"
    return "unknown"


def collect(prefix, node, scalars, groups, types, table_map=None):
    """把一个节点拆成标量字段和重复字段两组"""
    for key, value in node.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, list) and value and all(isinstance(x, dict) and not is_leaf(x) for x in value):
            groups.append((name, value))
        elif isinstance(value, list):
            scalars[name] = ", ".join(labeled(x, name, table_map) for x in value)
            types[name] = field_type(value[0]) if value else "unknown"
        elif isinstance(value, dict) and not is_leaf(value):
            collect(name, value, scalars, groups, types, table_map)
        else:
            scalars[name] = labeled(value, name, table_map)
            types[name] = field_type(value)


def flatten(prefix, node, table_map=None):
    """递归展开成若干扁平行，返回 (list[dict], 列名->类型)"""
    scalars, groups, types = {}, [], {}
    collect(prefix, node, scalars, groups, types, table_map)
    rows = [scalars]
    for name, items in groups:
        choices = []
        for item in items:
            sub_rows, sub_types = flatten(name, item, table_map)
            types.update(sub_types)
            choices.append(sub_rows)
        rows = [{**row, **sub} for row in rows for choice in choices for sub in choice]
    return rows, types


def row_of(headers, record, table_map, time_columns=(), time_format=None):
    """一行数据库记录 -> (主表行, [(blob 列, blob, 摘要前七位)])"""
    row, blobs = {}, []
    for header in headers:
        value = record[header]
        if not isinstance(value, bytes):
            row[header] = labeled(value, header, table_map, time_columns, time_format)
        elif not value:
            row[header] = ""
        else:
            digest = hashlib.sha256(value).hexdigest()[:7]
            row[header] = f"(hash:{digest})"
            blobs.append((header, value, digest))
    return row, blobs


def protobuf_cell(blob, limit):
    """消息出不了子表时的格子：长度不超过 limit 时连 hex 一起给，超过只留标记"""
    return f"(protobuf:hex:{blob.hex()})" if limit < 0 or len(blob) <= limit else "(protobuf)"


def json_rows(columns, records):
    """按列顺序构建 JSON 行对象：标量保留原生类型，消息 blob 就地内嵌。

    返回行对象与待裁剪的消息节点 (行对象, 列名, 节点)；裁剪结果需写回行对象。
    解不出消息的 blob 直接使用解码结果，不套节点包装。
    """
    rows, embedded = [], []
    for record in records:
        row = {}
        for header in columns:
            value = record[header]
            if not isinstance(value, bytes):
                row[header] = value
            elif not value:
                row[header] = ""
            else:
                node = as_node(value)
                if is_message(node["decoded"]):
                    row[header] = node
                    embedded.append((row, header, node))
                else:
                    row[header] = node["decoded"]
        rows.append(row)
    return rows, embedded


def blob_title(index, column, digest, count=None):
    """子表标题：来源行的 # 与列名、定位用的摘要，count 非空时附上展开行数"""
    head = f"#{index} {column}" + (f" (展开 {count} 行)" if count is not None else "")
    return f"{head}\nhash: {digest}"


def field_names(rows):
    """展开表内各列的先后，按首次出现排序"""
    names = []
    for row in rows:
        for name in row:
            if name not in names:
                names.append(name)
    return names


def tables_of(conn, db_path):
    """库中可选的表、行数，以及列与 protobuf 字段在 maps/ 的收录情况，排除 FTS 影子表与 sqlite 内部表"""
    names = [r[0] for r in conn.execute("SELECT name FROM pragma_table_list WHERE schema = 'main' AND type IN ('table', 'virtual') AND substr(name, 1, 7) <> 'sqlite_' ORDER BY name")]
    census = scan.census_of(db_path, render_progress)
    return [(name, conn.execute(f"SELECT count(*) FROM [{name}]").fetchone()[0], defined_columns(conn, db_path, name), defined_fields(db_path, name, census.get(name, {}))) for name in names]


def column_status(entry):
    """列映射状态键；None 表示已定义"""
    if entry is None:
        return "UNDEFINED"
    return entry.status.name if entry.status else None


def status_text(status):
    return {None: "已定义", "UNDEFINED": "未定义", "HIDDEN": "已隐藏", "DISCARDED": "已丢弃", "EXPLORING": "探索中"}.get(status, "未定义")


def columns_of(conn, db_path, table):
    """表的所有列、映射名称、状态键与枚举原文"""
    table_map = load_table_map(db_path, table)
    rows, statuses = [], []
    for (column,) in conn.execute("SELECT name FROM pragma_table_info(?)", (table,)):
        entry = table_map.entry(column)
        label = entry.name if entry and entry.name else ""
        status = column_status(entry)
        enum = "" if entry is None else str(entry.enum)
        rows.append([column, label, status_text(status), enum])
        statuses.append(status)
    return rows, statuses


def identifier(raw):
    if not IDENTIFIER.match(raw):
        raise argparse.ArgumentTypeError(f"非法表名: {raw}")
    return raw


def column_list(raw):
    """逗号分隔的列名列表；去除首尾空白，拒绝空项与重复"""
    names = [name.strip() for name in raw.split(",")]
    if any(not IDENTIFIER.match(name) for name in names):
        raise argparse.ArgumentTypeError(f"非法列名列表: {raw}")
    if len(set(names)) != len(names):
        raise argparse.ArgumentTypeError(f"列名重复: {raw}")
    return names


def defined_columns(conn, db_path, table):
    """返回 (数据库列中在 maps/ 有定义的列数, 列总数)，只比列名，不涉及 protobuf"""
    columns = [row[0] for row in conn.execute("SELECT name FROM pragma_table_info(?)", (table,))]
    table_map = load_table_map(db_path, table)
    return sum(1 for column in columns if table_map and column in table_map.columns), len(columns)


def column_is_blob(conn, table, column):
    row = conn.execute("SELECT type FROM pragma_table_info(?) WHERE name = ?", (table, column)).fetchone()
    return bool(row and "BLOB" in (row[0] or "").upper())


def defined_fields(db_path, table, census):
    """返回 (maps/ 登记的 protobuf 字段数, 扫描出的字段号种数)，状态不影响计入；
    字段号取路径末段与 maps/ 的键对齐，与列同号的最外层字段是该列的容器，不计入"""
    table_map = load_table_map(db_path, table)
    defined = sum(len(column.proto or {}) for column in table_map.columns.values()) if table_map else 0
    observed = {path.rsplit(".", 1)[-1] for column, entry in census.items() for path in entry["fields"] if path != column}
    return defined, len(observed)


def load_table_map(db_path, table):
    """加载 maps/ 下的映射表；库文件名与表名都命中才有效，否则给一张空表，未登记即未定义"""
    from maps import Table
    from maps.databases import for_file

    return for_file(db_path, table) or Table(table, {})


def labels_of(table_map, names):
    labels = {}
    for name in names:
        label = table_map.label(name)
        if label:
            labels[name] = label
    return labels


def field_states(names, table_map):
    """每个字段路径的着色档：未定义给 UNDEFINED，带状态的给其成员名，其余给 None"""
    states = {}
    for name in names:
        entry = table_map.entry(name)
        states[name] = "UNDEFINED" if entry is None else (entry.status.name if entry.status else None)
    return states


def visible_columns(names, table_map, show_undefined, show_hidden, show_discarded):
    """按状态开关筛出的列"""
    return [name for name in names if table_map.blocked(name, show_undefined, show_hidden, show_discarded) is None]


def path_chain(name):
    """字段路径自身与它的各级祖先"""
    parts = name.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts) + 1)]


def visible_fields(names, table_map, show_undefined, show_hidden, show_discarded):
    """要渲染的字段：祖先链上有一段被挡下，整棵子树都不渲染。

    二维表只把叶子摊成列，中间层不成为列也不参与查表，若只按叶子自身的路径判定，
    中间层被隐藏时子树仍会露出来，与 json 侧 prune 的结果不一致"""
    blocked = {prefix for name in names for prefix in path_chain(name) if table_map.blocked(prefix, show_undefined, show_hidden, show_discarded)}
    return [name for name in names if not blocked.intersection(path_chain(name))]


def blocked_reasons(names, table_map, show_undefined, show_hidden, show_discarded):
    """未渲染的列按原因计数，键取原因枚举的成员名"""
    reasons = Counter()
    for name in names:
        reason = table_map.blocked(name, show_undefined, show_hidden, show_discarded)
        if reason:
            reasons[reason.name] += 1
    return reasons


def matches_search(value, needles, ignore_case):
    """列值是否包含全部关键字；NULL 视为空串"""
    if isinstance(value, bytes):
        return False
    text = "" if value is None else str(value)
    if ignore_case:
        text = text.casefold()
    return all(needle in text for needle in needles)


def seen_blob_fields(records, columns, max_depth):
    """可见 blob 列解码出的全部字段路径，用于 values 模式的摘要统计"""
    seen = set()
    for record in records:
        for column in columns:
            value = record[column]
            if not isinstance(value, bytes) or not value:
                continue
            decoded = decode(value, max_depth=max_depth)
            if not is_message(decoded):
                continue
            expanded, _ = flatten("", decoded)
            fields = field_names(expanded)
            seen |= {prefix for name in fields for prefix in path_chain(name)}
    return seen


def merge_key(values):
    """按输出内容生成合并键；bytes 使用完整 hex 并与文本区分，其余类型不同但文本相同视为同一个键"""
    return tuple(("bytes", value.hex()) if isinstance(value, bytes) else (None if value is None else str(value)) for value in values)


def keep_small_groups(records, column, limit):
    """只保留列值分组的成员数不超过 limit 的行"""
    counts = Counter((type(record[column]), record[column]) for record in records)
    return [record for record in records if counts[(type(record[column]), record[column])] <= limit]


def random_rows(records, count, rng):
    """按当前顺序随机取 count 行; 不放回, count 超过行数时取全部"""
    if count >= len(records):
        return records
    indices = sorted(rng.sample(range(len(records)), count))
    return [records[index] for index in indices]


def reservoir_rows(conn, table, scope, count, rng):
    """只扫描 rowid 与 scope 标记, 用蓄水池取 count 个 (rowid, 原表次序)"""
    if count == 0:
        return []
    if scope:
        subset, params = conditions(scope)
        query = f"SELECT rowid, CASE WHEN {subset} THEN 1 ELSE 0 END FROM [{table}] ORDER BY rowid"
    else:
        params = []
        query = f"SELECT rowid FROM [{table}] ORDER BY rowid"

    picked = []
    seen = 0
    for position, row in enumerate(conn.execute(query, params), 1):
        if scope and not row[1]:
            continue
        if len(picked) < count:
            picked.append((row[0], position))
        else:
            slot = rng.randrange(seen + 1)
            if slot < count:
                picked[slot] = (row[0], position)
        seen += 1
    picked.sort(key=lambda item: item[1])
    return picked


def conditions(pairs):
    """若干 (列名, 值) 编成同时成立的条件，以及按序绑定的参数"""
    return " AND ".join(f"[{column}] = ?" for column, _ in pairs), [value for _, value in pairs]


def ordering_keys(order):
    """若干 (列名, 方向) 编成 SQL 的排序键，按给出的先后"""
    return ", ".join(f"[{column}] {direction.upper()}" for column, direction in order)


def row_query(table, first, latest, where=(), span=(0, 0), scope=(), order=()):
    """按 rowid 次序编出原表次序序号，三个选取条件互斥，因此至多只会用到其中一条。

    order 是选取次序：给出时另编一套序号，取开头、取末尾、命中与邻行都按这套序号计算，
    没有它时选取次序就是 rowid 顺序。它只决定取哪些行，不决定这些行怎么排。
    序号在过滤前编出，因此过滤后仍是原表次序中的序号。
    scope 先把参与选取的行限在它选出的集合内，取末尾时按集合的行数计，
    邻行按集合内的序号取，越过集合首尾由序号范围自然截断。
    显示的 # 始终是原表次序的序号，因此使用了 scope 或 order 就会跳号。
    where 是命中条件，span 为 (前若干行, 后若干行)，以命中行为锚一并取它的邻行。
    列名由调用方保证只含标识符字符，值走参数绑定"""
    if order:
        # 末尾补 rowid：并列行的先后不能交给 SQLite 决定，否则换了版本或查询计划就可能取到别的行
        numbered = f"SELECT ROW_NUMBER() OVER (ORDER BY rowid) AS [#], ROW_NUMBER() OVER (ORDER BY {ordering_keys(order)}, rowid) AS [o#], * FROM [{table}]"
        position = "[o#]"
    else:
        numbered = f"SELECT ROW_NUMBER() OVER (ORDER BY rowid) AS [#], * FROM [{table}]"
        position = "[#]"
    subset, scope_params = conditions(scope) if scope else ("1", [])
    # 限定集自带一套序号：有 scope 时是它选出的行，没有时就是整表。
    # 取开头、取末尾、命中与邻行都按这套序号算，输出仍带原表次序序号
    ranked = f"""WITH [s] AS (
    SELECT [n].*, ROW_NUMBER() OVER (ORDER BY {position}) AS [s#] FROM ({numbered}) AS [n] WHERE {subset}
)"""

    if first is not None:
        if scope:
            return f"{ranked} SELECT * FROM [s] WHERE [s#] <= {first}", scope_params
        return f"SELECT * FROM ({numbered}) AS [n] WHERE {position} <= {first}", []
    if latest is not None:
        if scope:
            return f"{ranked} SELECT * FROM [s] WHERE [s#] > (SELECT count(*) FROM [s]) - {latest}", scope_params
        return f"SELECT * FROM ({numbered}) AS [n] WHERE {position} > (SELECT count(*) FROM [{table}]) - {latest}", []
    if not where:
        # 没有选取条件时，限定条件本身就是唯一的筛选
        if scope:
            return f"SELECT * FROM ({numbered}) AS [n] WHERE {subset}", scope_params
        return numbered, []

    hits, hit_params = conditions(where)
    if not any(span):
        # 没有邻行时范围只是与命中条件一起筛选
        return f"SELECT * FROM ({numbered}) AS [n] WHERE {f'{subset} AND ' if scope else ''}{hits}", [*scope_params, *hit_params]

    before, after = span
    query = f"""{ranked}, [hit] AS (SELECT [s#] FROM [s] WHERE {hits})
SELECT * FROM [s] WHERE EXISTS (SELECT 1 FROM [hit] WHERE [s].[s#] BETWEEN [hit].[s#] - {before} AND [hit].[s#] + {after})"""
    return query, [*scope_params, *hit_params]


def condition(raw):
    """过滤条件写成 列名=值；值里可以再出现等号，只按首个等号切分"""
    column, sep, value = raw.partition("=")
    if not sep or not IDENTIFIER.match(column):
        raise argparse.ArgumentTypeError(f"过滤条件应为 列名=值: {raw}")
    return column, value


def ordering(raw):
    """排序列写成 列名 或 列名=asc / 列名=desc；省略方向按升序"""
    column, sep, direction = raw.partition("=")
    if not IDENTIFIER.match(column):
        raise argparse.ArgumentTypeError(f"非法排序列名: {raw}")
    if sep and direction not in ("asc", "desc"):
        raise argparse.ArgumentTypeError(f"排序方向应为 asc 或 desc: {raw}")
    return column, direction or "asc"


def non_negative(raw):
    """行数或邻行数：非负整数"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}")
    return value


def blob_limit(raw):
    """--short-blob 的字节长度上限；-1 表示不限制"""
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"应为 -1 或非负整数: {raw}") from None
    if value < -1:
        raise argparse.ArgumentTypeError(f"应为 -1 或非负整数: {raw}")
    return value


def group_limit(raw):
    """分组过滤写成 列名=N；N 为组内成员数上限"""
    column, sep, value = raw.partition("=")
    if not sep or not IDENTIFIER.match(column):
        raise argparse.ArgumentTypeError(f"分组过滤应为 列名=N: {raw}")
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}") from None
    if limit < 0:
        raise argparse.ArgumentTypeError(f"应为非负整数: {raw}")
    return column, limit


# 状态开关的紧凑写法：-Cuh 一类，后缀只能由 u/h/d 组成
CLUSTER = re.compile(r"^-([CP])([uhd]+)$")

# 紧凑写法展开成对应的长选项，后缀列出要显示的状态
SWITCHES = {
    ("C", "u"): "--show-undefined-columns",
    ("C", "h"): "--show-hidden-columns",
    ("C", "d"): "--show-discarded-columns",
    ("P", "u"): "--show-undefined-fields",
    ("P", "h"): "--show-hidden-fields",
    ("P", "d"): "--show-discarded-fields",
}


def expand_switches(parser, argv):
    """把 -Cuh / -Pud 展开成对应的长选项；-C、-P 与 -- 之后的内容原样交给解析器。

    后缀必须紧跟 -C 或 -P，-C u 这类分开写法不会被识别，-u/-h/-d 也不作为选项存在。
    后缀里重复给出同一状态只是重复设置，结果不变；多个开关同时给出时按并集合并。
    """
    expanded, literal = [], False
    for token in argv:
        if literal:
            expanded.append(token)
        elif token == "--":
            literal = True
            expanded.append(token)
        elif token in ("-C", "-P"):
            expanded.append(token)
        elif match := CLUSTER.match(token):
            group, statuses = match.groups()
            expanded += [SWITCHES[(group, status)] for status in statuses]
        elif token.startswith(("-C", "-P")):
            parser.error(f"{token}: 后缀只能由 u/h/d 组成")
        else:
            expanded.append(token)
    return expanded


def help_text(prog):
    colored = sys.stdout.isatty()
    bold = "\x1b[1m" if colored else ""
    title = "\x1b[1;4m" if colored else ""
    faint = "\x1b[2m" if colored else ""
    off = "\x1b[0m" if colored else ""
    return f"""{bold}{prog} -- SQLite 数据库与 Protobuf 研究逆向工具{off}

{title}用法:{off}
  {bold}{prog}{off} [选项] <db> [table]

{title}示例:{off}
  在用户信息贮藏缓存表中，选择好感度、昵称、备注，按照好感度倒序，取结果的前十条，结果只取值，隐藏摘要
  {prog} profile_info.db profile_info_v6 --select=20070,20002,20009 -o '20070=desc' --values -F 10 -q

  在用户信息贮藏缓存表中，按照好感度倒序，取结果的前十条，输出为 kv 风格，隐藏摘要
  {prog} profile_info.db profile_info_v6 -k -o '20070=desc' -F 10 -q

  在用户信息贮藏缓存表中，只显示昵称、备注，并在两者中搜索猫娘，取前十条，输出为 kv 风格，隐藏摘要
  {prog} profile_info.db profile_info_v6 -k --select=20002,20009 --search 猫娘 --search-columns=20002,20009 -F 10 -q

  在用户信息贮藏缓存表中，统计性别分布
  {prog} profile_info.db profile_info_v6 --count-by 20014

{title}参数:{off}
  {bold}db{off}                                   SQLite 数据库文件
  {bold}table{off}                                表名，缺省时列出库中的表

{title}选项 (排序; -O/-o 可重复，多个键按给出次序比较):{off}
  {bold}-O, --order-input <列名[=asc|desc]>{off}  在选取之前重排输入次序，只决定取哪些行
  {bold}-o, --order <列名[=asc|desc]>{off}        在所有选取之后重排已选行
      {faint}未给出 -o 时，输出顺序不作保证{off}

{title}选项 (选取范围; -f -l -w -r 互斥; -s/-w 可重复，条件按 AND 合并):{off}
  {bold}-s, --scope <列名=值>{off}                限定候选集
      {faint}-f/-l 在集合内计数，-w 的邻行不超出集合{off}
  {bold}-f, --first <N>{off}                      按输入次序只取开头 N 行
  {bold}-l, --latest <N>{off}                     按输入次序只取末尾 N 行
  {bold}-w, --where <列名=值>{off}                命中条件，需全部满足，不比较 blob 列
  {bold}-r, --random <N>{off}                     从限定候选集随机选取 N 行
      {faint}与 -f/-l/-w 互斥; 搜索与 -F/-L 在采样之后执行{off}
      {faint}无放回; N 超过候选数时取全部{off}

{title}选项 (扩展行数，需与 -w 同用，三者互斥):{off}
  {bold}-a, --after <N>{off}                      按输入次序，命中行之后 N 行一并渲染
  {bold}-b, --before <N>{off}                     按输入次序，命中行之前 N 行一并渲染
  {bold}-c, --context <N>{off}                    按输入次序，命中行前后各 N 行一并渲染

{title}选项 (列与搜索):{off}
  {bold}--select-columns <列名[,列名]>{off}       接管显示列; --select 为别名
      {faint}--select 与 --select-columns 不可同时使用{off}
      {faint}省略时显示所有可见列; 显式选择可显示隐藏列并不受 -C 过滤{off}
      {faint}适用 values/values-uniq 与 2d/kv/json; 与 -n/--count-by 同用时静默忽略{off}
  {bold}--search-columns <列名[,列名]>{off}       接管搜索列; 需与 --search 同用
      {faint}省略时搜索所有可见列; 显式可含隐藏列; BLOB 不参与匹配{off}
  {bold}--search <关键字串>{off}                  任一候选单元格含全部关键字即命中
      {faint}每个单元格独立按 AND 匹配; 任一单元格命中即整行命中{off}
      {faint}搜索列由 --search-columns 接管, 否则为所有可见列{off}
      {faint}数值按文本; 搜索默认区分大小写{off}
  {bold}--ignore-case{off}                        搜索时忽略大小写

{title}选项 (列清单):{off}
  {bold}--list-columns{off}                      列出所有列、映射名称、状态与枚举
      {faint}最高优先级; 忽略行相关选项与其它输出模式{off}

{title}选项 (最终截断，-F -L 互斥):{off}
  {bold}-F, --first-final <N>{off}                 取最终结果的前 N 行
  {bold}-L, --last-final <N>{off}                  取最终结果的后 N 行
      {faint}-F/-L 在选取、搜索、排序之后执行; 仍可与 -f/-l 组合{off}

{title}选项 (统计):{off}
  {bold}--count-by <列名[,列名...]>{off}          按列值逐层分组计数; 输出数量与百分比
      {faint}统计最终结果集; 允许隐藏列与 BLOB{off}
      {faint}BLOB 按完整 bytes 分组，显示遵守 --short-blob{off}
      {faint}多列时逐层嵌套; 占比以所属上级分组为分母{off}
      {faint}附加信息仅最后一层展开{off}
      {faint}优先级: count > count-by > values > 风格{off}
  {bold}--display-columns <列名[,列名]>{off}      附加信息列; 值为 JSON 标量; 允许 BLOB
      {faint}需与 --count-by 同用; 仅最后一层展开; 超过阈值的组显示 …{off}
  {bold}--display-limit <N>{off}                  组计数 <=N 时展开附加信息; 默认 10
      {faint}需与 --display-columns 同用; 0 不展开{off}
  {bold}--sort-by <asc|desc>{off}                 按分组列的值排序; 并列按数量降序
      {faint}需与 --count-by 同用; NULL 始终最后{off}
      {faint}嵌套时主表和子表都按该方向排序{off}
  {bold}--parent-count{off}                       count-by 子表增加父级数列
      {faint}需至少两层 --count-by; 父级数 >1 时终端标红{off}
      {faint}父级数为该值在当前结果集中出现的不同直接父值数{off}
  {bold}--no-guides{off}                          count-by 表不显示层级连接线
      {faint}默认显示; 需与 --count-by 同用{off}
  {bold}--count-by-padding <N>{off}               count-by 表内水平内边距; 默认 2
      {faint}表内单元格左右各 N 格; 最左侧固定为 0{off}
      {faint}垂直内边距保持 0; 需与 --count-by 同用{off}

{title}选项 (分组过滤):{off}
  {bold}--keep-groups <列名=N>{off}               仅保留组计数 <=N 的组; 需配 --values
      {faint}分组按最终结果集; 分组列可为隐藏列与 BLOB{off}

{title}选项 (随机采样):{off}
  {bold}--sample <N>{off}                         从最终结果随机采样 N 行
      {faint}在 -F/-L 与分组过滤之后执行; 保持原顺序{off}
      {faint}无放回; N 超过当前行数时取全部{off}
  {bold}--random-seed <N>{off}                    随机种子; 需与 -r 或 --sample 同用
      {faint}不指定时每次结果不同; 两个采样阶段共用同一序列{off}

{title}选项 (按状态过滤):{off}
  {bold}-C[uhd], --show-all-columns{off}          渲染列
  {bold}-P[uhd], --show-all-fields{off}           渲染 Protobuf 字段
      {faint}后缀 u/h/d 表示未定义/已隐藏/已丢弃，省略时显示全部状态{off}
      {faint}探索中状态始终可见并标紫，不参与 -C/-P 过滤{off}
      {faint}必须紧跟 -C 或 -P，可连写，如 -Cuh{off}
    {bold}--show-undefined-columns{off}           渲染未定义的列
    {bold}--show-hidden-columns{off}              渲染已隐藏的列
    {bold}--show-discarded-columns{off}           渲染已丢弃的列
    {bold}--show-undefined-fields{off}            渲染未定义的 Protobuf 字段
    {bold}--show-hidden-fields{off}               渲染已隐藏的 Protobuf 字段
    {bold}--show-discarded-fields{off}            渲染已丢弃的 Protobuf 字段

{title}选项 (解析):{off}
  {bold}--max-depth <N>{off}                      Protobuf 嵌套层数上限，默认 16
  {bold}--short-blob <N>{off}                     BLOB 显示附带完整 hex 的字节长度上限，默认 16
      {faint}超过上限只显示 (blob)/(protobuf); -1 表示不限制; 空 BLOB 显示 (empty){off}

{title}选项 (输出):{off}
  {bold}-n, --count{off}                          仅输出主表最终行数; 最高优先级
  {bold}--values{off}                             按显示列顺序逗号连接各列值; 优先于风格
      {faint}未选择时按表列顺序使用所有可见列; 行首显示 # 行号{off}
      {faint}BLOB 遵守 --short-blob; 空 BLOB 为 (empty){off}
  {bold}--values-uniq{off}                        按完整原始值合并连续行; 行首显示 N x，不显示行号
      {faint}--values 与 --values-uniq 互斥; 未选择时同上{off}
  {bold}-j, --json{off}                           等价于 --style json
  {bold}-k, --kv{off}                             等价于 --style kv
  {bold}--style <2d|kv|json>{off}                 输出风格
      {faint}-j/--json、-k/--kv、--style 三者互斥{off}
  {bold}--nohex{off}                              仅 json 风格: 不输出 hex 字段

{title}选项 (时间):{off}
  {bold}--time-format <格式>{off}                 strftime 格式; 缺省 %Y-%m-%d %H:%M:%S
      {faint}秒/毫秒按 2000-2100 年自动判定; 仅 2d/kv、values/values-uniq、count-by/附加信息{off}
  {bold}--time-columns <列名[,列名]>{off}         需要格式化的顶层列
      {faint}JSON 保持原值; 允许隐藏的非 blob 列{off}
  {bold}--auto-time{off}                          自动检测时间列; 与 --time-columns 互斥
      {faint}整表每列取样最多 100 个非零、非 NULL 值; 全部有效且单位一致{off}
      {faint}不做列语义过滤，可能将纯数字标识符列误判为时间列{off}

{title}选项 (诊断):{off}
  {bold}-q, --no-summary{off}                     不显示总摘要

{title}选项 (程序):{off}
  {bold}-h, --help{off}                           显示本帮助
"""


class HelpParser(argparse.ArgumentParser):
    """帮助文本由 help_text() 提供，不随子命令变化。"""

    def format_help(self):
        return help_text(self.prog)


def main():
    parser = HelpParser(prog="Table2D")
    parser.add_argument("db")
    parser.add_argument("table", type=identifier, nargs="?")
    picking = parser.add_mutually_exclusive_group()
    picking.add_argument("-f", "--first", type=non_negative, metavar="N")
    picking.add_argument("-l", "--latest", type=non_negative, metavar="N")
    picking.add_argument("-w", "--where", type=condition, action="append", metavar="列名=值")
    picking.add_argument("-r", "--random", type=non_negative, metavar="N")
    parser.add_argument("-s", "--scope", type=condition, action="append", metavar="列名=值")
    parser.add_argument("--select-columns", "--select", dest="select_columns", type=column_list, action="append", metavar="列名[,列名]")
    parser.add_argument("--search-columns", type=column_list, action="append", metavar="列名[,列名]")
    parser.add_argument("--search", action="append", metavar="关键字串")
    parser.add_argument("--ignore-case", action="store_true")
    parser.add_argument("--list-columns", action="store_true")
    final = parser.add_mutually_exclusive_group()
    final.add_argument("-F", "--first-final", type=non_negative, metavar="N")
    final.add_argument("-L", "--last-final", type=non_negative, metavar="N")
    expanding = parser.add_mutually_exclusive_group()
    expanding.add_argument("-a", "--after", type=non_negative, metavar="N")
    expanding.add_argument("-b", "--before", type=non_negative, metavar="N")
    expanding.add_argument("-c", "--context", type=non_negative, metavar="N")
    parser.add_argument("-O", "--order-input", type=ordering, action="append", metavar="列名[=asc|desc]")
    parser.add_argument("-o", "--order", type=ordering, action="append", metavar="列名[=asc|desc]")
    parser.add_argument("--show-undefined-columns", action="store_true")
    parser.add_argument("--show-hidden-columns", action="store_true")
    parser.add_argument("--show-discarded-columns", action="store_true")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("-j", "--json", action="store_true")
    output.add_argument("-k", "--kv", action="store_true")
    output.add_argument("--style", choices=("2d", "kv", "json"), default="2d")
    parser.add_argument("-n", "--count", action="store_true")
    parser.add_argument("--count-by", type=column_list, action="append", metavar="列名[,列名...]")
    parser.add_argument("--display-columns", type=column_list, action="append", metavar="列名[,列名]")
    parser.add_argument("--display-limit", type=non_negative, metavar="N")
    parser.add_argument("--sort-by", choices=("asc", "desc"))
    parser.add_argument("--parent-count", action="store_true")
    parser.add_argument("--no-guides", action="store_true")
    parser.add_argument("--count-by-padding", type=non_negative, metavar="N")
    parser.add_argument("--sample", type=non_negative, metavar="N")
    parser.add_argument("--random-seed", type=int, metavar="N")
    value_mode = parser.add_mutually_exclusive_group()
    value_mode.add_argument("--values", action="store_true")
    value_mode.add_argument("--values-uniq", action="store_true")
    parser.add_argument("--keep-groups", type=group_limit, action="append", metavar="列名=N")
    parser.add_argument("--nohex", action="store_true")
    parser.add_argument("--time-format", metavar="格式")
    parser.add_argument("--time-columns", type=column_list, action="append", metavar="列名[,列名]")
    parser.add_argument("--auto-time", action="store_true")
    parser.add_argument("-q", "--no-summary", action="store_true")
    parser.add_argument("--show-undefined-fields", action="store_true")
    parser.add_argument("--show-hidden-fields", action="store_true")
    parser.add_argument("--show-discarded-fields", action="store_true")
    parser.add_argument("-P", "--show-all-fields", action="store_true")
    parser.add_argument("-C", "--show-all-columns", action="store_true")
    parser.add_argument("--max-depth", type=non_negative, default=16, metavar="N")
    parser.add_argument("--short-blob", type=blob_limit, default=16, metavar="N")
    args = parser.parse_args(expand_switches(parser, sys.argv[1:]))
    if args.json:
        args.style = "json"
    elif args.kv:
        args.style = "kv"

    # 列清单是独立模式: 最高优先级, 不触发行选取与其它输出选项
    if args.list_columns:
        if args.table is None:
            parser.error("--list-columns 需指定表")
        conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows, statuses = columns_of(conn, args.db, args.table)
        if not rows:
            parser.error(f"表不存在: {args.table}")
        render_small_table(rows, ["列", "映射名称", "状态", "枚举"], row_styles=status_row_styles(statuses))
        return

    if args.auto_time and args.time_columns is not None:
        parser.error("--auto-time 与 --time-columns 不能同时指定")
    if args.time_format is not None and not args.auto_time and args.time_columns is None:
        parser.error("--time-format 需与 --time-columns 或 --auto-time 同用")
    if args.time_columns is not None and len(args.time_columns) != 1:
        parser.error("--time-columns 只能指定一次")
    time_columns = set(args.time_columns[0]) if args.time_columns else set()
    if args.time_format is not None and not args.time_format:
        parser.error("--time-format 不能为空")
    time_format = args.time_format if args.time_format is not None else DEFAULT_TIME_FORMAT
    try:
        datetime(2000, 1, 1).strftime(time_format)
    except ValueError as exc:
        parser.error(f"--time-format 无效: {exc}")

    # --select-columns 只接管显示；搜索列由 --search-columns 单独接管
    if args.select_columns is not None and len(args.select_columns) != 1:
        parser.error("--select-columns/--select 只能指定一次")
    select_columns = args.select_columns[0] if args.select_columns else []
    count_options = resolve_options(args, parser)
    if args.random_seed is not None and args.random is None and args.sample is None:
        parser.error("--random-seed 需与 --random 或 --sample 同用")
    rng = random.Random(args.random_seed) if args.random_seed is not None else random
    if args.keep_groups is not None and len(args.keep_groups) != 1:
        parser.error("--keep-groups 只能指定一次")
    keep_groups = args.keep_groups[0] if args.keep_groups else None
    if keep_groups is not None and not args.values:
        parser.error("--keep-groups 需与 --values 同用")
    if args.search_columns is not None and len(args.search_columns) != 1:
        parser.error("--search-columns 只能指定一次")
    search_column_args = args.search_columns[0] if args.search_columns else []
    if search_column_args and args.search is None:
        parser.error("--search-columns 需与 --search 同用")
    if args.search is not None and len(args.search) != 1:
        parser.error("--search 只能指定一次")
    if args.ignore_case and args.search is None:
        parser.error("--ignore-case 需与 --search 同用")
    search_tokens = args.search[0].split() if args.search else []
    if args.search is not None and not search_tokens:
        parser.error("--search 的关键字不能为空")

    # 扩展行数围绕命中行取邻行，只能配 -w
    if args.where is None and any(value is not None for value in (args.after, args.before, args.context)):
        parser.error("-a/-b/-c 需与 -w 同用")
    before = args.before or args.context or 0
    after = args.after or args.context or 0

    # -P 与 -C 是三档开关的简写，展开后再走同一套判定
    if args.show_all_fields:
        args.show_undefined_fields = args.show_hidden_fields = args.show_discarded_fields = True
    if args.show_all_columns:
        args.show_undefined_columns = args.show_hidden_columns = args.show_discarded_columns = True

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # TEXT 不保证是合法 UTF-8；替换无效字节，避免取行阶段抛错
    conn.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
    if args.table is None:
        if select_columns and not args.count and count_options is None:
            parser.error("--select-columns 需指定表")
        if search_column_args:
            parser.error("--search-columns 需指定表")
        if args.search is not None:
            parser.error("--search 需指定表")
        if args.values:
            parser.error("--values 需指定表")
        if args.values_uniq:
            parser.error("--values-uniq 需指定表")
        if args.count:
            parser.error("--count 需指定表")
        if count_options is not None:
            parser.error("--count-by 需指定表")
        if args.time_columns is not None:
            parser.error("--time-columns 需指定表")
        if args.auto_time:
            parser.error("--auto-time 需指定表")
        if args.first_final is not None or args.last_final is not None:
            parser.error("-F/-L 需指定表")
        if args.random is not None:
            parser.error("--random 需指定表")
        if args.sample is not None:
            parser.error("--sample 需指定表")
        render_tables(tables_of(conn, args.db))
        return

    if args.auto_time:
        time_columns = detect_time_columns(conn, args.table)

    # 查询自带原表次序序号与选取序号，其余是表列
    if args.random is not None:
        picked = reservoir_rows(conn, args.table, args.scope or [], args.random, rng)
        conn.execute("CREATE TEMP TABLE [__table2d_picked] (rid INTEGER, n INTEGER)")
        conn.executemany("INSERT INTO [__table2d_picked] VALUES (?, ?)", picked)
        query = f"SELECT [p].[n] AS [#], [t].* FROM [__table2d_picked] AS [p] JOIN [{args.table}] AS [t] ON [t].rowid = [p].rid"
        if args.order:
            # 输出排序是最后一步，只作用于已经选出的行
            query += f" ORDER BY {ordering_keys(args.order)}, [#]"
        else:
            query += " ORDER BY [#]"
        params = []
    else:
        query, params = row_query(args.table, args.first, args.latest, args.where or [], (before, after), args.scope or [], args.order_input or [])
        if args.order:
            # 输出排序是最后一步，只作用于已经选出的行
            query += f" ORDER BY {ordering_keys(args.order)}, [#]"
    cursor = conn.execute(query, params)
    headers = [name for name in (d[0] for d in cursor.description) if name not in COMPUTED_COLUMNS]
    records = cursor.fetchall()

    table_map = load_table_map(args.db, args.table)
    # 子表标题靠 # 与列名定位，主表中未显示的列既不进入 json 的行对象，也不为它生成子表
    shown = set(visible_columns(headers, table_map, args.show_undefined_columns, args.show_hidden_columns, args.show_discarded_columns))
    shown_columns = [name for name in headers if name in shown]
    view_columns = select_columns or shown_columns
    view_set = set(view_columns)
    search_columns = search_column_args or shown_columns
    undisplayed = [name for name in headers if name not in view_set]
    if args.search is not None and not search_columns:
        records = []
    if (args.values or args.values_uniq) and not view_columns:
        records = []

    if count_options is not None:
        validate_columns(count_options, headers, parser)

    for column in time_columns:
        if column not in headers:
            parser.error(f"表中没有列: {column}")
        if column_is_blob(conn, args.table, column):
            parser.error(f"列 {column} 是二进制列，不能用于时间格式化")
        if any(isinstance(record[column], bytes) for record in records):
            parser.error(f"列 {column} 的值包含二进制数据，不能用于时间格式化")

    if keep_groups is not None:
        column, _ = keep_groups
        if column not in headers:
            parser.error(f"表中没有列: {column}")

    # 显式选择接管显示，不再受 shown 限制；count/count-by 优先时静默忽略选择列
    if not args.count and count_options is None:
        for column in select_columns:
            if column not in headers:
                parser.error(f"表中没有列: {column}")
    # 搜索列可包含隐藏列与 BLOB；BLOB 单元格由 matches_search 跳过
    for column in search_column_args:
        if column not in headers:
            parser.error(f"表中没有列: {column}")
    if args.search is not None:
        needles = [token.casefold() for token in search_tokens] if args.ignore_case else search_tokens
        records = [record for record in records if any(matches_search(record[column], needles, args.ignore_case) for column in search_columns)]

    # 最终截断在搜索之后执行; 下游输出都只看截断后的 records
    if args.first_final is not None:
        records = records[: args.first_final]
    elif args.last_final is not None:
        records = [] if args.last_final == 0 else records[-args.last_final:]

    if keep_groups is not None:
        records = keep_small_groups(records, *keep_groups)

    if args.sample is not None:
        records = random_rows(records, args.sample, rng)

    # count 是独立输出模式: 只报告最终行数, 不渲染表格与摘要
    if args.count:
        render_count(len(records))
        return

    # count-by 输出列值统计; 优先级高于 values 与风格
    if count_options is not None:
        entries = build_entries(records, count_options, table_map)
        value_format = ValueFormat(frozenset(time_columns), time_format, args.short_blob, args.max_depth)
        render_count_by(entries, count_options, len(records), value_format)
        return

    # values 与 values-uniq 只输出选中列的值; 摘要仍按 --no-summary 控制
    if args.values or args.values_uniq:
        if not args.no_summary:
            seen_fields = seen_blob_fields(records, view_columns, args.max_depth)
            column_reasons = blocked_reasons(undisplayed, table_map, args.show_undefined_columns, args.show_hidden_columns, args.show_discarded_columns)
            field_reasons = blocked_reasons(seen_fields, table_map, args.show_undefined_fields, args.show_hidden_fields, args.show_discarded_fields)
            render_summary(column_reasons, field_reasons)
        if args.values_uniq:
            runs = []
            previous_key = None
            previous_values = None
            count = 0
            for record in records:
                raw_values = tuple(record[column] for column in view_columns)
                key = merge_key(raw_values)
                if count and key == previous_key:
                    count += 1
                    continue
                if count:
                    runs.append((previous_values, count))
                previous_key = key
                previous_values = tuple(value_json(value, column, time_columns, time_format, args.short_blob, args.max_depth) for column, value in zip(view_columns, raw_values))
                count = 1
            if count:
                runs.append((previous_values, count))
            render_values(runs)
        else:
            for record in records:
                marker = row_marker(record["#"])
                print(f"{marker} {join_values(value_json(record[column], column, time_columns, time_format, args.short_blob, args.max_depth) for column in view_columns)}")
        return

    # json 的行对象自己编：标量保留原生类型，blob 就地内嵌，不做显示用的字符串化与摘要
    if args.style == "json":
        rows, embedded = json_rows(view_columns, records)
        seen_fields = {name for *_, node in embedded for name in node_paths(node)}
        hidden = seen_fields - set(visible_columns(seen_fields, table_map, args.show_undefined_fields, args.show_hidden_fields, args.show_discarded_fields))
        for row, column, node in embedded:
            node = prune(node, hidden)
            row[column] = without_hex(node) if args.nohex else node
        if not args.no_summary:
            column_reasons = blocked_reasons(undisplayed, table_map, args.show_undefined_columns, args.show_hidden_columns, args.show_discarded_columns)
            field_reasons = blocked_reasons(seen_fields, table_map, args.show_undefined_fields, args.show_hidden_fields, args.show_discarded_fields)
            render_summary(column_reasons, field_reasons)
        # 列键与字段键共用一套映射，labels 与 states 因此要覆盖两者，列名才带得上语义名与状态色
        paths = [*view_columns, *seen_fields]
        render_rows("json", f"{args.table} (展开 {len(rows)} 行)", rows, view_columns, {}, labels_of(table_map, paths), field_states(paths, table_map))
        return

    labels = labels_of(table_map, headers)
    column_states = field_states(headers, table_map)

    view_index = {name: index for index, name in enumerate(view_columns)}
    main_rows, blobs = [], []
    for record in records:
        row, found = row_of(headers, record, table_map, time_columns, time_format)
        main_rows.append({"#": str(record["#"]), **row})
        for column, blob, digest in sorted(found, key=lambda item: view_index.get(item[0], len(view_columns))):
            if column in view_set:
                blobs.append((record["#"], column, blob, digest))
    rows_by_number = {row["#"]: row for row in main_rows}

    # 字段级规则决定每个 blob 能否出子表：出不成的按原因改写主表格子
    #   消息但字段全被挡下 -> (protobuf)；非消息 -> 值直接给在格子里（文本原样，字节给 hex）
    tables, seen_fields = [], set()
    for index, column, blob, digest in blobs:
        decoded = decode(blob, max_depth=args.max_depth)
        if not is_message(decoded):
            rows_by_number[str(index)][column] = cell(decoded)
            continue
        expanded, types = flatten("", decoded, table_map)
        fields = field_names(expanded)
        # 普查收全部路径而不只是叶子：中间层同样会被挡下，是子树的截断点，与 json 侧 node_paths 对齐
        seen_fields |= {prefix for name in fields for prefix in path_chain(name)}
        fields = visible_fields(fields, table_map, args.show_undefined_fields, args.show_hidden_fields, args.show_discarded_fields)
        if fields:
            tables.append((index, column, expanded, types, digest, fields))
        else:
            rows_by_number[str(index)][column] = protobuf_cell(blob, args.short_blob)

    if not args.no_summary:
        column_reasons = blocked_reasons(undisplayed, table_map, args.show_undefined_columns, args.show_hidden_columns, args.show_discarded_columns)
        field_reasons = blocked_reasons(seen_fields, table_map, args.show_undefined_fields, args.show_hidden_fields, args.show_discarded_fields)
        render_summary(column_reasons, field_reasons)

    names = ["#"] + view_columns
    main_rows = [{name: row[name] for name in names if name in row} for row in main_rows]
    render_rows(args.style, f"{args.table} (展开 {len(main_rows)} 行)", main_rows, names, {}, labels, column_states)

    for index, column, expanded, types, digest, fields in tables:
        types = {name: kind for name, kind in types.items() if name in fields}
        field_labels = labels_of(table_map, fields)
        field_colors = field_states(fields, table_map)
        render_rule()
        render_rows(args.style, blob_title(index, column, digest, len(expanded)), expanded, fields, types, field_labels, field_colors, f"{column}.")


if __name__ == "__main__":
    main()
