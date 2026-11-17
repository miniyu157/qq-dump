"""数据访问层: 好友清单、主人信息、群资料查询。

库文件无法打开或读取时抛 DatabaseError，消息可直接展示给用户。
群资料来自 profile_info.db 之外的 group_info.db，由调用方单独提供。
"""

from .errors import DatabaseError
from .friends import Friend, load_friends, load_owner
from .group_info import Bulletin, CustomLabel, Essence, GroupAddress, GroupDetail, GroupMember, GroupNotice, NoticeMember
from .group_info import load_bulletins, load_details, load_essences, load_members, load_notices

__all__ = [
    "Bulletin",
    "CustomLabel",
    "DatabaseError",
    "Essence",
    "Friend",
    "GroupAddress",
    "GroupDetail",
    "GroupMember",
    "GroupNotice",
    "NoticeMember",
    "load_bulletins",
    "load_details",
    "load_essences",
    "load_friends",
    "load_members",
    "load_notices",
    "load_owner",
]
