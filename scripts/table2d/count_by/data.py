"""count-by 的统计数据处理：分组树、排序、父级计数与显示条目。"""

from functools import cmp_to_key
from typing import NamedTuple

from .options import Options


def value_category(value):
    """排序时的类型组：布尔、数值、字符串、其它、NULL"""
    if value is None:
        return 5
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return 1
    if isinstance(value, str):
        return 2
    return 3


def sort_text(value):
    """其它类型的排序键：bytes 使用完整 hex，其余使用字符串表示"""
    return value.hex() if isinstance(value, bytes) else str(value)


def compare_stat(left, right, direction):
    """值排序：NULL 始终最后，类型组顺序固定，方向只作用于同类；并列按数量降序"""
    left_value, left_count, _ = left
    right_value, right_count, _ = right
    left_category = value_category(left_value)
    right_category = value_category(right_value)
    if left_category != right_category:
        return (left_category > right_category) - (left_category < right_category)
    if left_category != 5:
        if left_category == 3:
            left_key, right_key = sort_text(left_value), sort_text(right_value)
        else:
            left_key, right_key = left_value, right_value
        if left_key != right_key:
            if direction == "asc":
                return (left_key > right_key) - (left_key < right_key)
            return (left_key < right_key) - (left_key > right_key)
    return (right_count > left_count) - (right_count < left_count)


def stat_order(item):
    """默认排序键：数量降序，并列时数值/字符串升序，NULL 最后"""
    value, count, _ = item
    if value is None:
        order = (3, 0, "")
    elif isinstance(value, bool):
        order = (0, int(value), "")
    elif isinstance(value, (int, float)):
        order = (1, value, "")
    elif isinstance(value, str):
        order = (2, 0, value)
    else:
        order = (4, 0, sort_text(value))
    return (-count, order)


class StatNode:
    """统计树节点；children 在构建期为字典，排序后为列表。"""

    __slots__ = ("value", "count", "children", "records")

    def __init__(self, value, records):
        self.value = value
        self.count = 0
        self.children = {}
        self.records = records


StatEntry = NamedTuple("StatEntry", [("value", object), ("name", object), ("count", int), ("records", object), ("parents", object), ("children", list)])


def stat_tree(records, columns, direction, detail_limit):
    """按列序列逐层分组；最后一层按阈值保留附加信息样本，其余层不保留记录。"""
    last = len(columns) - 1
    root = {}
    for record in records:
        level = root
        for index, column in enumerate(columns):
            value = record[column]
            key = (type(value), value)
            node = level.get(key)
            if node is None:
                node = StatNode(value, [] if index == last and detail_limit else None)
                level[key] = node
            node.count += 1
            if index == last and node.records is not None:
                if node.count <= detail_limit:
                    node.records.append(record)
                else:
                    node.records = None
            level = node.children
    return order_tree(root, direction)


def order_tree(level, direction):
    """按统计排序规则逐层排序；children 由构建期的字典改为列表。"""
    nodes = list(level.values())
    if direction is None:
        nodes.sort(key=lambda node: stat_order((node.value, node.count, None)))
    else:
        nodes.sort(key=cmp_to_key(lambda left, right: compare_stat((left.value, left.count, None), (right.value, right.count, None), direction)))
    for node in nodes:
        node.children = order_tree(node.children, direction)
    return nodes


def parent_counts(nodes, depth):
    """每个层级的值 -> 出现过的不同直接父值集合; level 0 无父级"""
    counts = [None] * depth
    for level in range(1, depth):
        counts[level] = {}

    def walk(nodes, level, parent_key=None):
        for node in nodes:
            key = (type(node.value), node.value)
            if level:
                counts[level].setdefault(key, set()).add(parent_key)
            walk(node.children, level + 1, key)

    walk(nodes, 0)
    return counts


def stat_entries(nodes, columns, level, table_map, parents=None):
    """统计树 -> 未格式化的条目树。"""
    entries = []
    for node in nodes:
        if node.children:
            children = stat_entries(node.children, columns, level + 1, table_map, parents)
        else:
            children = []
        key = (type(node.value), node.value)
        parent_count = len(parents[level].get(key, ())) if parents is not None and level else None
        entries.append(StatEntry(
            node.value,
            table_map.enum(columns[level], node.value) if node.value is not None else None,
            node.count,
            node.records,
            parent_count,
            children,
        ))
    return entries


def build_entries(records, options: Options, table_map):
    """按 options 构建 count-by 的原始条目树"""
    tree = stat_tree(records, options.columns, options.sort_by, options.display_limit)
    parents = parent_counts(tree, len(options.columns)) if options.parent_count else None
    return stat_entries(tree, options.columns, 0, table_map, parents)
