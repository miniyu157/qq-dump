#!/usr/bin/env python3
"""通过命令行试用终端确认；提示输出到 stderr，结果以 JSON 输出到 stdout。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.tui.choose import ChoiceCancelled
from lib.tui.confirm import confirm

__all__ = []


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default="确认继续？", help="提示文本")
    parser.add_argument("--default", action=argparse.BooleanOptionalAction, default=True, help="初始选中肯定项")
    parser.add_argument("--affirmative", default="是", help="肯定项标签")
    parser.add_argument("--negative", default="否", help="否定项标签")
    parser.add_argument("--no-divider", action="store_true", help="不显示结束分隔线")
    args = parser.parse_args()

    try:
        result = confirm(args.prompt, divider=not args.no_divider, default=args.default, affirmative=args.affirmative, negative=args.negative)
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
