"""maps/ 条目状态的显示文字与 rich 样式。"""

from typing import NamedTuple

from maps import Status

__all__ = ["STATUS_LABELS", "StatusLabel"]


class StatusLabel(NamedTuple):
    text: str
    style: str | None


# None 对应已登记但未设置状态的条目
STATUS_LABELS: dict[Status | None, StatusLabel] = {
    None: StatusLabel("已定义", None),
    Status.UNDEFINED: StatusLabel("未定义", "dim"),
    Status.HIDDEN: StatusLabel("已隐藏", "yellow"),
    Status.DISCARDED: StatusLabel("已丢弃", "red"),
    Status.EXPLORING: StatusLabel("探索中", "magenta"),
}
