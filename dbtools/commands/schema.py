"""schema 子命令组 —— 数据库结构发现与代码生成。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

import typer

from ..codegen import add_columns, add_db, add_empty_db, add_empty_table, remove_db, remove_table
from ..discover import get_columns_by_files, get_tables_by_files
from .explore import explore

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True, add_help_option=False)

app.command(name="explore", no_args_is_help=True)(explore)


@app.callback()
def _callback() -> None:
    """数据库结构发现与代码生成。"""


@app.command("d-tables", no_args_is_help=True)
def discover_tables(
    files: list[str] = typer.Argument(help="数据库文件路径（一个或多个）"),
) -> None:
    """从数据库文件发现所有用户表名，输出 JSON。"""
    try:
        result = get_tables_by_files(*files)
    except (ValueError, sqlite3.Error, OSError) as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(code=1)
    print(json.dumps(result, ensure_ascii=False))


@app.command("d-columns", no_args_is_help=True)
def discover_columns(
    table: str = typer.Argument(help="目标表名"),
    files: list[str] = typer.Argument(help="数据库文件路径（一个或多个）"),
) -> None:
    """从数据库文件发现指定表的列信息，输出 JSON。"""
    try:
        cols = get_columns_by_files(*files, table=table)
    except (ValueError, sqlite3.Error, OSError) as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(code=1)
    result = [asdict(c) for c in cols]
    print(json.dumps(result, ensure_ascii=False))


@app.command("add", no_args_is_help=True)
def add_cmd(
    db: str = typer.Argument(help="数据库名称，即 Database.filename"),
    table: str | None = typer.Argument(None, help="可选：指定表名"),
    from_db_files: list[str] | None = typer.Option(
        None, "--from-db-files", "-f", help="数据库文件路径（一个或多个），用于发现"
    ),
) -> None:
    """创建/填充 schema 数据库或表。不指定 -f 时为手工模式，指定 -f 时从 SQLite 文件发现结构。"""
    try:
        if from_db_files is None:
            if table is None:
                add_empty_db(db)
                typer.echo(f"  {db}: 已创建空数据库")
            else:
                add_empty_table(db, table)
                typer.echo(f"  {db}/{table}: 已添加空表")
        else:
            if table is None:
                tables = get_tables_by_files(*from_db_files)
                if not tables:
                    typer.echo(f"  {db}: 未发现用户表")
                    return
                add_db(db, tables)
                typer.echo(f"  {db}: 已生成 {len(tables)} 个表")
            else:
                add_columns(db, table, *from_db_files)
                typer.echo(f"  {db}/{table}: 列信息已更新")
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("full-auto-add", no_args_is_help=True)
def full_auto_add_cmd(
    db: str = typer.Argument(help="数据库名称，即 Database.filename"),
    from_db_files: list[str] = typer.Option(
        ..., "--from-db-files", "-f", help="数据库文件路径（一个或多个），用于发现"
    ),
) -> None:
    """从数据库文件发现表结构和全部列信息，一键生成完整 schema。"""
    try:
        tables = get_tables_by_files(*from_db_files)
        if not tables:
            typer.echo(f"  {db}: 未发现用户表")
            return
        add_db(db, tables)
        typer.echo(f"  {db}: 已生成 {len(tables)} 个表")
        for table_name in tables:
            add_columns(db, table_name, *from_db_files)
            typer.echo(f"    {table_name}: 列信息已更新")
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("remove", no_args_is_help=True)
def remove_cmd(
    db: str = typer.Argument(help="数据库名称，即 Database.filename"),
    tables: list[str] = typer.Argument(None, help="表名（可指定多个），不指定时移除整个数据库"),
) -> None:
    """安全移除数据库或表。"""
    try:
        if not tables:
            remove_db(db)
            typer.echo(f"  {db}: 已移除数据库")
        else:
            remove_table(db, *tables)
            for t in tables:
                typer.echo(f"  {db}/{t}: 已移除表")
    except ValueError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(code=1)
