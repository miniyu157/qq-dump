"""在输出末尾附加提示。"""

from collections.abc import Sequence

from rich.console import Console

__all__ = ["render_tip"]


def render_tip(lines: Sequence[str]) -> None:
    """向 stderr 输出一条 dim 分割线，再输出 TIP: 与逐行缩进的 lines；stdout 不受影响。"""
    console = Console(stderr=True, soft_wrap=True, markup=False, emoji=False, highlight=False)
    console.rule(style="dim")
    console.print("TIP:")
    for line in lines:
        console.print(f"  {line}")
