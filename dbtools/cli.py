"""CLI 入口 —— Typer 应用定义、全局选项、子命令注册。"""

from __future__ import annotations

import os

os.environ["TYPER_USE_RICH"] = "0"

from typing import Annotated

import typer

from .commands.group import app as group_app
from .commands.info import app as info_app
from .commands.schema import app as schema_app


app = typer.Typer(no_args_is_help=True, add_completion=False, add_help_option=False)
app.add_typer(info_app, name="info")
app.add_typer(group_app, name="group")
app.add_typer(schema_app, name="schema")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    msg_db: Annotated[
        str | None,
        typer.Option("--msg-db", "-m", help="消息数据库 nt_msg.db 路径。"),
    ] = None,
    profile_db: Annotated[
        str | None,
        typer.Option("--profile-db", "-p", help="用户信息数据库 profile_info.db 路径。"),
    ] = None,
) -> None:
    """QQNT数据库的数据交互后端。"""
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit()
    ctx.ensure_object(dict)
    ctx.obj["msg_db"] = msg_db
    ctx.obj["profile_db"] = profile_db
