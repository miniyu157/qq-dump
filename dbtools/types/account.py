"""用户账号信息。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountInfo:
    """用户账号信息。默认值即 DB NULL 时的回退值。"""

    uid: str = ""
    qid: str = ""
    uin: int = 0
    nickname: str = ""
    birthday_year: int | None = None
    birthday_month: int | None = None
    birthday_day: int | None = None
    alias: str | None = None
    signature: str | None = None
    gender: str = "unset"  # 经过 GENDER_MAP 映射
