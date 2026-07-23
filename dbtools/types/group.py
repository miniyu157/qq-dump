"""好友分组。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FriendGroup:
    """好友分组。"""

    group_id: int = 0
    group_name: str = ""
    member_count: int = 0
