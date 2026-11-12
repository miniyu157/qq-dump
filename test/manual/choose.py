#!/usr/bin/env python3
"""通过命令行试用终端选择器；菜单输出到 stderr，结果以 JSON 输出到 stdout。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.tui.choose import ChoiceCancelled, choose, choose_many

__all__ = []


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("options", nargs="+", help="选项文本，至少一个")
    parser.add_argument("--multiple", action="store_true", help="启用多选")
    parser.add_argument("--title", default="", help="菜单标题")
    parser.add_argument("--height", type=int, default=10, help="每页项数，默认 10")
    parser.add_argument("--initial", type=int, default=0, help="初始光标下标，从 0 开始")
    parser.add_argument("--selected", type=int, nargs="+", help="多选预选下标，从 0 开始")
    parser.add_argument("--no-divider", action="store_true", help="不显示结束分隔线")
    args = parser.parse_args()
    if args.selected is not None and not args.multiple:
        parser.error("--selected 仅允许与 --multiple 一起使用")

    settings = {"title": args.title, "height": args.height, "initial": args.initial, "divider": not args.no_divider}
    try:
        if args.multiple:
            result = choose_many(args.options, selected=args.selected or (), **settings)
        else:
            result = choose(args.options, **settings)
    except (ChoiceCancelled, EOFError):
        return 1
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        parser.error(str(exc))

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
