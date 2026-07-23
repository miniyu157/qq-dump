"""用户信息查询子命令。"""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from ..info import get_by_uid, get_my_info

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True, add_help_option=False)


@app.callback()
def _callback() -> None:
    """用户信息查询。"""


def _json(data: object) -> None:
    """输出格式化的 JSON（AccountInfo 或 None）。"""
    if data is None:
        print("null")
    else:
        print(json.dumps(asdict(data), ensure_ascii=False, indent=2))


@app.command("uid")
def uid(ctx: typer.Context, target: str) -> None:
    """按 UID 查询用户信息。"""
    _json(get_by_uid(ctx.obj["profile_db"], target))


@app.command("my")
def my(ctx: typer.Context) -> None:
    """查询主人账号信息。"""
    _json(get_my_info(ctx.obj["profile_db"]))
