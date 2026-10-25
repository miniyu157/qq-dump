#!/usr/bin/env python3
"""统计标准输入中第四个 JSON 值的文件名后缀。

每行是一组逗号分隔的 JSON 值；取第四个值作为文件名，后缀统一转小写统计。
NULL 与空字符串归为 (空值)，无后缀归为 (无后缀)。
"""

import json
import re
import sys
from collections import Counter
from pathlib import PurePath

from rich.cells import cell_len

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def fourth_value(line):
    """逗号分隔的一行 JSON 值 -> 第四个标量"""
    values = json.loads(f"[{line}]")
    return values[3]


def suffix_of(value):
    if value is None or value == "":
        return "(空值)"
    suffix = PurePath(str(value)).suffix
    return suffix.lower() if suffix else "(无后缀)"


def main():
    counts = Counter()
    for raw in sys.stdin:
        line = ANSI.sub("", raw).strip()
        if not line:
            continue
        try:
            value = fourth_value(line)
        except (json.JSONDecodeError, IndexError) as exc:
            print(f"跳过无法解析的行: {line} ({exc})", file=sys.stderr)
            continue
        counts[suffix_of(value)] += 1

    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    names = [name for name, _ in items]
    total = sum(counts.values())
    width = max((cell_len(name) for name in names), default=0)
    print(" ".join(names))
    print(", ".join(names))
    for name, count in items:
        percent = f"{count / total:.2%}" if total else "0.00%"
        print(f"{name}{' ' * (width - cell_len(name))}  {count:>6}  {percent:>7}")
    percent = "100.00%" if total else "0.00%"
    print(f"总计{' ' * (width - cell_len('总计'))}  {total:>6}  {percent:>7}")


if __name__ == "__main__":
    main()
