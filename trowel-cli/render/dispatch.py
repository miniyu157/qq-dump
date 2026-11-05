"""按输出形式选择渲染函数。"""

from typing import Literal

from render.sheet import Sheet
from render.show2d import render_2d
from render.showjson import render_json
from render.showkv import render_kv

__all__ = ["Form", "show"]

Form = Literal["table", "kv", "json"]

_RENDERERS = {"table": render_2d, "kv": render_kv, "json": render_json}


def show(sheet: Sheet, *, form: Form) -> None:
    """按 form 把 sheet 输出到 stdout。"""
    _RENDERERS[form](sheet)
