import sys

try:
    from rich import print
    from rich.console import Console
    from rich.progress import track
    from rich.rule import Rule

    console = Console()
except ImportError:
    print("使用 'pip install -r requirements.txt' 安装缺少的依赖包。")
    sys.exit(1)


def error(msg: str) -> None:
    print(f"[bold red]错误[/bold red]: {msg}", file=sys.stderr)


def msg1(msg: str) -> None:
    print(f"[bold green]➜ [/bold green]{msg}")


def msg2(msg: str) -> None:
    print(f"[bold green]  ➜ [/bold green]{msg}")
