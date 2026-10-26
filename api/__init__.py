"""数据访问层: 好友清单与主人信息查询。

库文件无法打开、读取或未登记映射时抛 DatabaseError，消息可直接展示给用户。
"""

from .errors import DatabaseError
from .friends import Friend, load_friends, load_owner

__all__ = ["DatabaseError", "Friend", "load_friends", "load_owner"]
