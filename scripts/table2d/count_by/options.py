"""count-by 的参数校验与配置。"""

from argparse import ArgumentParser
from dataclasses import dataclass


@dataclass(frozen=True)
class Options:
    columns: tuple[str, ...]
    display_columns: tuple[str, ...]
    display_limit: int
    sort_by: str | None
    parent_count: bool
    guides: bool
    padding: int


def resolve_options(args, parser: ArgumentParser) -> Options | None:
    """校验 count-by 选项并返回配置；未使用 count-by 时返回 None"""
    if args.count_by is not None and len(args.count_by) != 1:
        parser.error("--count-by 只能指定一次")
    columns = tuple(args.count_by[0]) if args.count_by else ()
    if args.display_columns is not None and len(args.display_columns) != 1:
        parser.error("--display-columns 只能指定一次")
    display_columns = tuple(args.display_columns[0]) if args.display_columns else ()
    if display_columns and not columns:
        parser.error("--display-columns 需与 --count-by 同用")
    if display_columns:
        display_limit = args.display_limit if args.display_limit is not None else 10
    elif args.display_limit is not None:
        parser.error("--display-limit 需与 --display-columns 同用")
    else:
        display_limit = 0
    if args.sort_by is not None and not columns:
        parser.error("--sort-by 需与 --count-by 同用")
    if args.no_guides and not columns:
        parser.error("--no-guides 需与 --count-by 同用")
    if args.count_by_padding is not None and not columns:
        parser.error("--count-by-padding 需与 --count-by 同用")
    padding = args.count_by_padding if args.count_by_padding is not None else 2
    if args.parent_count and not columns:
        parser.error("--parent-count 需与 --count-by 同用")
    if args.parent_count and len(columns) < 2:
        parser.error("--parent-count 需至少两层 --count-by")
    if not columns:
        return None
    return Options(columns, display_columns, display_limit, args.sort_by, args.parent_count, not args.no_guides, padding)


def validate_columns(options: Options, headers: list[str], parser: ArgumentParser) -> None:
    """统计列与附加信息列必须存在；类型限制由具体输出逻辑处理"""
    for column in options.columns:
        if column not in headers:
            parser.error(f"表中没有列: {column}")
    for column in options.display_columns:
        if column not in headers:
            parser.error(f"表中没有列: {column}")
