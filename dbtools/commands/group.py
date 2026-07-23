"""好友分组查询子命令。"""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from ..groups import list_groups

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True, add_help_option=False)


@app.callback()
def _callback() -> None:
    """好友分组查询。"""


@app.command("list")
def list_command(ctx: typer.Context) -> None:
    """列出所有好友分组，输出 JSON。"""
    groups = list_groups(ctx.obj["profile_db"])
    print(json.dumps([asdict(g) for g in groups], ensure_ascii=False, indent=2))
