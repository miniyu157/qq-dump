#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def scan_accounts(root: Path) -> list[dict[str, str]]:
    accounts = []
    pattern = "data/user/*/com.tencent.mobileqq/files/uid/*"
    for uid_path in sorted(root.glob(pattern)):
        uin, _, uid = uid_path.name.partition("###")
        user = uid_path.parents[3].name
        accounts.append({"user": user, "uid": uid, "uin": uin})
    return accounts


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描 QQ NT 账号")
    parser.add_argument("-r", "--root-dir", default="/", help="根目录，默认为 /")
    args = parser.parse_args()

    root = Path(args.root_dir).expanduser().resolve()
    print(json.dumps(scan_accounts(root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(f"错误: {exc}")
